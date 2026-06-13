"use client";

import { useRef, useState } from "react";

interface FileUploaderProps {
  accept: string;
  label: string;
  onUpload: (file: File) => Promise<void>;
  loading: boolean;
}

export default function FileUploader({ accept, label, onUpload, loading }: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) setSelectedFile(file);
  }

  async function handleUploadClick() {
    if (selectedFile) {
      await onUpload(selectedFile);
      setSelectedFile(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragOver ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400 hover:bg-gray-50"
        }`}
      >
        <input ref={inputRef} type="file" accept={accept} onChange={handleFileChange} className="hidden" />
        <p className="text-gray-500 text-sm">
          {selectedFile ? (
            <span className="text-blue-600 font-medium">{selectedFile.name}</span>
          ) : (
            <>Drag and drop or click to select — <span className="text-blue-600">{label}</span></>
          )}
        </p>
      </div>
      {selectedFile && (
        <button
          onClick={handleUploadClick}
          disabled={loading}
          className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Uploading..." : "Upload"}
        </button>
      )}
    </div>
  );
}
