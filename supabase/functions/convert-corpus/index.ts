// convert-corpus
//
// Accepts a multipart upload of a `.zip` containing source documents
// (.epub, .pdf, .text, .tei, .html, .xml). Writes the archive to ephemeral
// `/tmp` storage, returns 202 immediately, and runs the conversion to `.exg`
// inside an `EdgeRuntime.waitUntil` background task — following:
// https://supabase.com/docs/guides/functions/ephemeral-storage
//
// Background task steps:
//   1. Read the zip from /tmp
//   2. Detect the dominant source format from file extensions
//   3. Build the .exg envelope (manifest.json + index.json + corpus.exgc)
//   4. Upload to <bucket>/datasets/{name}.exg
//   5. Remove the original from <bucket>/uploads/{job_id}.zip
//   6. Insert a row into public.corpora

import dotenvx from "npm:@dotenvx/dotenvx@^1.63.0";
import { createClient } from "npm:@supabase/supabase-js@2";
import JSZip from "npm:jszip@3.10.1";

declare const EdgeRuntime: { waitUntil(p: Promise<unknown>): void };

const SUPABASE_URL = dotenvx.get("SUPABASE_URL");
const SERVICE_KEY = dotenvx.get("SUPABASE_SECRET_KEY");
const BUCKET = "corpora";

const EXTENSION_TO_FORMAT: Record<string, string> = {
  ".epub": "application/epub+xml",
  ".html": "text/html",
  ".htm": "text/html",
  ".xml": "application/xml",
  ".tei": "application/tei+xml",
  ".pdf": "application/pdf",
  ".txt": "text/plain",
  ".text": "text/plain",
};

addEventListener("beforeunload", (ev) => {
  console.log("convert-corpus shutting down:", ev.detail?.reason);
});

addEventListener("unhandledrejection", (ev) => {
  console.error("convert-corpus unhandled rejection:", ev.reason);
  ev.preventDefault();
});

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return json({ error: "Method Not Allowed" }, 405);
  }

  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return json({ error: "Expected multipart/form-data" }, 400);
  }

  const file = form.get("file");
  if (!(file instanceof File) || !file.name.toLowerCase().endsWith(".zip")) {
    return json({ error: "field 'file' must be a .zip" }, 400);
  }

  const metadata = readMetadata(form);
  const missing = ["name", "type", "language", "period", "repository"].filter(
    (k) => !metadata[k as keyof CorpusMetadata],
  );
  if (missing.length || metadata.category.length === 0) {
    return json(
      {
        error: `Missing required fields: ${[...missing, ...(metadata.category.length === 0 ? ["category"] : [])].join(", ")}`,
      },
      400,
    );
  }

  const jobId = crypto.randomUUID();
  const tmpPath = `/tmp/${jobId}.zip`;
  const uploadPath = `uploads/${jobId}.zip`;

  const buffer = new Uint8Array(await file.arrayBuffer());

  // Per the tutorial: write to ephemeral /tmp so the background task can read it
  // without holding the request body open.
  await Deno.writeFile(tmpPath, buffer);

  // Mirror the upload to durable storage so the original is recoverable until
  // conversion succeeds.
  const supabase = createClient(SUPABASE_URL, SERVICE_KEY);
  const { error: uploadErr } = await supabase.storage.from(BUCKET).upload(uploadPath, buffer, {
    contentType: "application/zip",
    upsert: true,
  });
  if (uploadErr) {
    await safeRemoveTmp(tmpPath);
    return json({ error: `Storage upload failed: ${uploadErr.message}` }, 500);
  }

  EdgeRuntime.waitUntil(processArchive({ jobId, tmpPath, uploadPath, metadata, supabase }));

  return json({ job_id: jobId, status: "processing", upload_path: uploadPath }, 202);
});

// ── Background task ──────────────────────────────────────────────────────────

async function processArchive(args: ProcessArgs): Promise<void> {
  const { jobId, tmpPath, uploadPath, metadata, supabase } = args;
  console.log(`[${jobId}] starting conversion`);

  try {
    const zipBytes = await Deno.readFile(tmpPath);
    const inputZip = await JSZip.loadAsync(zipBytes);

    const sourceFormat = detectFormat(inputZip);
    const exgBytes = await buildExg(inputZip, metadata.name);

    const datasetPath = `datasets/${metadata.name}.exg`;
    const { error: putErr } = await supabase.storage.from(BUCKET).upload(datasetPath, exgBytes, {
      contentType: "application/zip",
      upsert: true,
    });
    if (putErr) throw new Error(`upload datasets/: ${putErr.message}`);

    const { error: rmErr } = await supabase.storage.from(BUCKET).remove([uploadPath]);
    if (rmErr) console.warn(`[${jobId}] failed to remove ${uploadPath}: ${rmErr.message}`);

    const { data: pub } = supabase.storage.from(BUCKET).getPublicUrl(datasetPath);

    const { error: dbErr } = await supabase.from("corpora").insert({
      uuid: crypto.randomUUID(),
      name: metadata.name,
      type: metadata.type,
      format: sourceFormat,
      language: metadata.language,
      period: metadata.period,
      repository: metadata.repository,
      category: metadata.category,
      description: metadata.description ?? null,
      licence: metadata.licence ?? null,
      credits: metadata.credits ?? null,
      download_uri: pub.publicUrl,
      size: humanSize(exgBytes.byteLength),
      version: 1,
      created_at: new Date().toISOString(),
    });
    if (dbErr) throw new Error(`insert corpora: ${dbErr.message}`);

    console.log(`[${jobId}] complete: ${datasetPath}`);
  } catch (err) {
    console.error(`[${jobId}] conversion failed:`, err);
  } finally {
    await safeRemoveTmp(tmpPath);
  }
}

// ── .exg builder (port of py-exegia/utils/convert_to_exg.py) ─────────────────

async function buildExg(input: JSZip, name: string): Promise<Uint8Array> {
  const tfFiles = Object.values(input.files).filter((f) => !f.dir && f.name.endsWith(".tf"));

  const otext = input.file(/(^|\/)otext\.tf$/i)[0];
  const otype = input.file(/(^|\/)otype\.tf$/i)[0];

  const otextMeta = otext ? parseTfHeader(await otext.async("string")) : {};
  const otypeMeta = otype ? parseTfHeader(await otype.async("string")) : {};

  const totalSize = await sumUncompressedSize(input);
  const sectionTypes = splitCsv(otextMeta.sectionTypes);
  const sectionFeatures = splitCsv(otextMeta.sectionFeatures);
  const textFormats: Record<string, string> = {};
  for (const [k, v] of Object.entries(otextMeta)) {
    if (k.startsWith("fmt:")) textFormats[k.slice(4)] = v;
  }

  const manifest = {
    format: "exg",
    format_version: "1.0",
    name: otextMeta.name ?? name,
    version: otextMeta.version ?? otypeMeta.version ?? "",
    description: otextMeta.description ?? otypeMeta.description ?? "",
    written_by: otextMeta.writtenBy ?? otypeMeta.writtenBy ?? "",
    date_written: otextMeta.dateWritten ?? otypeMeta.dateWritten ?? "",
    section_types: sectionTypes,
    section_features: sectionFeatures,
    text_formats: textFormats,
    node_types: otype ? collectNodeTypes(await otype.async("string")) : [],
    source_folder: name,
    tf_file_count: tfFiles.length,
    total_size_bytes: totalSize,
  };

  const index = await Promise.all(
    tfFiles
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(async (f) => ({
        path: f.name,
        size_bytes: (await f.async("uint8array")).byteLength,
      })),
  );

  // corpus.exgc — zip of the source dataset (we just hand back the input bytes
  // since it's already a zip with the same logical contents).
  const corpusExgc = await input.generateAsync({
    type: "uint8array",
    compression: "DEFLATE",
  });

  const exg = new JSZip();
  exg.file("manifest.json", JSON.stringify(manifest, null, 2));
  exg.file("index.json", JSON.stringify(index, null, 2));
  exg.file("corpus.exgc", corpusExgc);
  // .git placeholder — empty marker so consumers know this is a versioned exg.
  exg.folder(".git");
  exg.file(".git/HEAD", "ref: refs/heads/main\n");

  return await exg.generateAsync({
    type: "uint8array",
    compression: "DEFLATE",
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function readMetadata(form: FormData): CorpusMetadata {
  return {
    name: (form.get("name") as string) ?? "",
    type: (form.get("type") as string) ?? "",
    language: (form.get("language") as string) ?? "",
    period: (form.get("period") as string) ?? "",
    repository: (form.get("repository") as string) ?? "",
    category: form.getAll("category").map(String).filter(Boolean),
    description: (form.get("description") as string) ?? undefined,
    licence: (form.get("licence") as string) ?? undefined,
    credits: (form.get("credits") as string) ?? undefined,
  };
}

function detectFormat(zip: JSZip): string {
  const counts: Record<string, number> = {};
  for (const f of Object.values(zip.files)) {
    if (f.dir) continue;
    const dot = f.name.lastIndexOf(".");
    if (dot < 0) continue;
    const ext = f.name.slice(dot).toLowerCase();
    const fmt = EXTENSION_TO_FORMAT[ext];
    if (fmt) counts[fmt] = (counts[fmt] ?? 0) + 1;
  }
  const entries = Object.entries(counts);
  if (entries.length === 0) return "application/zip";
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0][0];
}

function parseTfHeader(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    if (raw === "") break;
    if (!raw.startsWith("@")) continue;
    const body = raw.slice(1);
    const eq = body.indexOf("=");
    if (eq >= 0) {
      out[body.slice(0, eq).trim()] = body.slice(eq + 1).trim();
    } else {
      out[body.trim()] = "";
    }
  }
  return out;
}

function collectNodeTypes(text: string): string[] {
  const seen = new Set<string>();
  const types: string[] = [];
  let inData = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!inData) {
      if (line === "") inData = true;
      continue;
    }
    if (!line || line.startsWith("#")) continue;
    const parts = line.split("\t");
    const t = parts[parts.length - 1].trim();
    if (t && !seen.has(t)) {
      seen.add(t);
      types.push(t);
    }
  }
  return types;
}

function splitCsv(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

async function sumUncompressedSize(zip: JSZip): Promise<number> {
  let total = 0;
  for (const f of Object.values(zip.files)) {
    if (f.dir) continue;
    const bytes = await f.async("uint8array");
    total += bytes.byteLength;
  }
  return total;
}

function humanSize(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  for (let i = 0; i < units.length; i++) {
    if (v < 1024 || i === units.length - 1) {
      return i === 0 ? `${v.toFixed(0)} ${units[i]}` : `${v.toFixed(1)} ${units[i]}`;
    }
    v /= 1024;
  }
  return `${bytes} B`;
}

async function safeRemoveTmp(path: string): Promise<void> {
  try {
    await Deno.remove(path);
  } catch {
    // ignore
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
