"use client";

import { useState, useEffect, useRef } from "react";
import Navbar from "@/components/Navbar";
import FileUploader from "@/components/FileUploader";
import BiomarkerTable from "@/components/BiomarkerTable";
import { apiClient, uploadWithProgress } from "@/lib/api";
import type { BloodTestUploadResult, AppleHealthUploadResult, NutritionUploadResult, Document } from "@/lib/types";

function parseDuplicateDoc(errMsg: string): Document | null {
  try {
    const json = errMsg.replace(/^[^{]*/, "");
    return JSON.parse(json).document ?? null;
  } catch {
    return null;
  }
}

function DocList({
  docs,
  deletingId,
  onDelete,
}: {
  docs: Document[];
  deletingId: string | null;
  onDelete: (id: string) => void;
}) {
  if (docs.length === 0) return null;
  return (
    <div className="mt-4 space-y-1.5">
      {docs.map((doc) => (
        <div key={doc.id} className="flex items-center justify-between bg-page rounded-lg px-3 py-2 border border-white/[0.06]">
          <div className="min-w-0">
            <span className="text-sm text-ink truncate block">{doc.filename}</span>
            <span className="text-[11px] text-muted">
              {doc.metadata?.test_date
                ? `${doc.metadata.lab_name ?? ""} · ${doc.metadata.test_date}`
                : doc.metadata?.first_date
                ? `${doc.metadata.first_date} → ${(doc.metadata as Record<string, string>).last_date ?? ""}`
                : doc.upload_date.slice(0, 10)}
            </span>
          </div>
          <div className="flex items-center gap-3 shrink-0 ml-3">
            <span className={`text-[10px] px-2 py-0.5 rounded-full ${doc.processed ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"}`}>
              {doc.processed ? "Processed" : "Pending"}
            </span>
            <button
              onClick={() => onDelete(doc.id)}
              disabled={deletingId === doc.id}
              className="text-xs text-muted hover:text-bad disabled:opacity-40 transition-colors"
            >
              {deletingId === doc.id ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

function UploadProgressOverlay({
  progress,
  title,
  stage,
}: {
  progress: number;
  title: string;
  stage: "uploading" | "processing" | "done";
}) {
  const stageLabel =
    stage === "uploading" ? "Uploading file…" :
    stage === "processing" ? "Processing on server…" :
    "Complete!";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-card border border-white/[0.08] rounded-2xl px-8 py-7 w-80 space-y-5 shadow-2xl">
        <div>
          <p className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-1">{title}</p>
          <p className="text-sm text-ink">{stageLabel}</p>
        </div>

        <div className="space-y-2">
          <div className="h-2 bg-white/[0.06] rounded-full overflow-hidden">
            <div
              className="h-full bg-hblue rounded-full transition-all duration-300 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-right text-xs font-mono text-muted">{progress}%</p>
        </div>
      </div>
    </div>
  );
}

export default function UploadPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const [btResult, setBtResult] = useState<BloodTestUploadResult | null>(null);
  const [btError, setBtError] = useState("");
  const [btDupDoc, setBtDupDoc] = useState<Document | null>(null);

  const [ahResult, setAhResult] = useState<AppleHealthUploadResult | null>(null);
  const [ahError, setAhError] = useState("");
  const [ahDupDoc, setAhDupDoc] = useState<Document | null>(null);

  const [nuResult, setNuResult] = useState<NutritionUploadResult | null>(null);
  const [nuError, setNuError] = useState("");
  const [nuDupDoc, setNuDupDoc] = useState<Document | null>(null);

  // Shared upload progress
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadStage, setUploadStage] = useState<"uploading" | "processing" | "done">("uploading");
  const processingTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  function clearProcessingTimer() {
    if (processingTimer.current) {
      clearInterval(processingTimer.current);
      processingTimer.current = null;
    }
  }

  function startProcessing(slowMode: boolean) {
    setUploadStage("processing");
    // slowMode = blood test (LLM inference); fast = nutrition/apple health
    const increment = slowMode ? 0.25 : 2.0;
    const interval = slowMode ? 400 : 100;
    processingTimer.current = setInterval(() => {
      setUploadProgress((p) => (p !== null && p < 95 ? parseFloat((p + increment).toFixed(1)) : p));
    }, interval);
  }

  function finishUpload() {
    clearProcessingTimer();
    setUploadStage("done");
    setUploadProgress(100);
    setTimeout(() => setUploadProgress(null), 1500);
  }

  function failUpload() {
    clearProcessingTimer();
    setUploadProgress(null);
  }

  async function loadDocuments() {
    try {
      const data = await apiClient.get<{ documents: Document[] }>("/api/ingest/documents");
      setDocuments(data.documents);
    } catch { /* silent */ }
  }

  useEffect(() => { loadDocuments(); }, []);

  async function handleDelete(docId: string) {
    setDeletingId(docId);
    try {
      await apiClient.delete(`/api/ingest/documents/${docId}`);
      await loadDocuments();
    } finally {
      setDeletingId(null);
    }
  }

  async function handleBloodTest(file: File) {
    setBtError(""); setBtResult(null); setBtDupDoc(null);
    setUploadTitle("Blood Test Report");
    setUploadStage("uploading");
    setUploadProgress(0);

    try {
      const fd = new FormData();
      fd.append("file", file);
      const data = await uploadWithProgress<BloodTestUploadResult>(
        "/api/ingest/blood-test",
        fd,
        (pct) => setUploadProgress(pct),
        () => startProcessing(true),
      );
      finishUpload();
      setBtResult(data);
      await loadDocuments();
    } catch (err) {
      failUpload();
      const msg = err instanceof Error ? err.message : "Upload failed";
      if (msg.includes("duplicate")) {
        setBtDupDoc(parseDuplicateDoc(msg));
        setBtError("duplicate");
      } else {
        setBtError(msg);
      }
    }
  }

  async function handleAppleHealth(file: File) {
    setAhError(""); setAhResult(null); setAhDupDoc(null);
    setUploadTitle("Apple Health Export");
    setUploadStage("uploading");
    setUploadProgress(0);

    try {
      const fd = new FormData();
      fd.append("file", file);
      const data = await uploadWithProgress<AppleHealthUploadResult>(
        "/api/ingest/apple-health",
        fd,
        (pct) => setUploadProgress(pct),
        () => startProcessing(false),
      );
      finishUpload();
      setAhResult(data);
      await loadDocuments();
    } catch (err) {
      failUpload();
      const msg = err instanceof Error ? err.message : "Upload failed";
      if (msg.includes("duplicate")) {
        setAhDupDoc(parseDuplicateDoc(msg));
        setAhError("duplicate");
      } else {
        setAhError(msg);
      }
    }
  }

  async function handleNutrition(file: File) {
    setNuError(""); setNuResult(null); setNuDupDoc(null);
    setUploadTitle("Nutrition Data");
    setUploadStage("uploading");
    setUploadProgress(0);

    try {
      const fd = new FormData();
      fd.append("file", file);
      const data = await uploadWithProgress<NutritionUploadResult>(
        "/api/ingest/nutrition",
        fd,
        (pct) => setUploadProgress(pct),
        () => startProcessing(false),
      );
      finishUpload();
      setNuResult(data);
      await loadDocuments();
    } catch (err) {
      failUpload();
      const msg = err instanceof Error ? err.message : "Upload failed";
      if (msg.includes("duplicate")) {
        setNuDupDoc(parseDuplicateDoc(msg));
        setNuError("duplicate");
      } else {
        setNuError(msg);
      }
    }
  }

  const btDocs = documents.filter((d) => d.source === "blood_test");
  const ahDocs = documents.filter((d) => d.source === "apple_health");
  const nuDocs = documents.filter((d) => d.source === "lose_it");

  return (
    <div className="min-h-screen bg-page">
      <Navbar />

      {uploadProgress !== null && (
        <UploadProgressOverlay
          progress={Math.round(uploadProgress)}
          title={uploadTitle}
          stage={uploadStage}
        />
      )}

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-8">

        {/* Blood Test */}
        <section className="bg-card rounded-xl border border-white/[0.08] p-6 space-y-4">
          <div>
            <p className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-0.5">Blood Test</p>
            <p className="text-xs text-muted">Upload a PDF from any lab — biomarkers are extracted automatically.</p>
          </div>
          <FileUploader accept=".pdf" label="Blood test PDF" onUpload={handleBloodTest} loading={uploadProgress !== null} />
          {btError === "duplicate" ? (
            <div className="text-sm rounded-lg px-3 py-2 bg-warn/10 border border-warn/20 text-warn">
              This file has already been uploaded
              {btDupDoc?.metadata?.test_date && (
                <span className="text-warn/80">
                  {" "}({btDupDoc.metadata.lab_name ? `${btDupDoc.metadata.lab_name}, ` : ""}test date {btDupDoc.metadata.test_date})
                </span>
              )}.
            </div>
          ) : btError ? (
            <p className="text-sm text-bad">{btError}</p>
          ) : null}
          <DocList docs={btDocs} deletingId={deletingId} onDelete={handleDelete} />
          {btResult && (
            <div className="space-y-3 pt-2">
              <div className="flex gap-4 text-xs text-muted">
                {btResult.lab_name && <span>Lab: <span className="text-ink">{btResult.lab_name}</span></span>}
                {btResult.test_date && <span>Date: <span className="text-ink">{btResult.test_date}</span></span>}
                <span>Biomarkers: <span className="text-ink">{btResult.biomarkers_extracted}</span></span>
              </div>
              <BiomarkerTable biomarkers={btResult.biomarkers} />
            </div>
          )}
        </section>

        {/* Apple Health */}
        <section className="bg-card rounded-xl border border-white/[0.08] p-6 space-y-4">
          <div>
            <p className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-0.5">Apple Health</p>
            <p className="text-xs text-muted">Export from the Health app on your iPhone and upload the ZIP — steps, sleep, heart rate, and more.</p>
          </div>
          <FileUploader accept=".zip" label="Apple Health export.zip" onUpload={handleAppleHealth} loading={uploadProgress !== null} />
          {ahError === "duplicate" ? (
            <div className="text-sm rounded-lg px-3 py-2 bg-warn/10 border border-warn/20 text-warn">
              This export has already been uploaded
              {ahDupDoc && <span className="text-warn/80"> (uploaded {ahDupDoc.upload_date.slice(0, 10)})</span>}.
            </div>
          ) : ahError ? (
            <p className="text-sm text-bad">{ahError}</p>
          ) : null}
          <DocList docs={ahDocs} deletingId={deletingId} onDelete={handleDelete} />
          {ahResult && (
            <div className="space-y-2 pt-2">
              <p className="text-xs text-muted"><span className="text-ink font-medium">{ahResult.metrics_inserted}</span> data points imported.</p>
              {Object.keys(ahResult.breakdown).length > 0 && (
                <div className="grid grid-cols-2 gap-x-6 gap-y-0.5 text-xs text-muted">
                  {Object.entries(ahResult.breakdown).sort((a, b) => b[1] - a[1]).map(([name, count]) => (
                    <div key={name} className="flex justify-between">
                      <span>{name.replace(/_/g, " ")}</span>
                      <span className="text-ink">{count} days</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

        {/* Nutrition */}
        <section className="bg-card rounded-xl border border-white/[0.08] p-6 space-y-4">
          <div>
            <p className="text-[11px] font-semibold text-muted uppercase tracking-widest mb-0.5">Nutrition (Lose It)</p>
            <p className="text-xs text-muted">Export your daily macro summary CSV from Lose It — calories, protein, carbs, fat, and more.</p>
          </div>
          <FileUploader accept=".csv" label="Lose It daily macro summary CSV" onUpload={handleNutrition} loading={uploadProgress !== null} />
          {nuError === "duplicate" ? (
            <div className="text-sm rounded-lg px-3 py-2 bg-warn/10 border border-warn/20 text-warn">
              This file has already been uploaded
              {nuDupDoc?.metadata && (
                <span className="text-warn/80">
                  {" "}({(nuDupDoc.metadata as Record<string, string>).first_date} → {(nuDupDoc.metadata as Record<string, string>).last_date})
                </span>
              )}.
            </div>
          ) : nuError ? (
            <p className="text-sm text-bad">{nuError}</p>
          ) : null}
          <DocList docs={nuDocs} deletingId={deletingId} onDelete={handleDelete} />
          {nuResult && (
            <div className="flex gap-6 pt-2 text-xs text-muted">
              <span><span className="text-ink font-medium">{nuResult.days_parsed}</span> days</span>
              <span><span className="text-ink font-medium">{nuResult.metrics_stored}</span> metrics</span>
              {nuResult.date_range && (
                <span>{nuResult.date_range.first} → {nuResult.date_range.last}</span>
              )}
            </div>
          )}
        </section>

      </main>
    </div>
  );
}
