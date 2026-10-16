/**
 * Uploads a file DIRECTLY from the browser to the video provider (VdoCipher's storage, or the
 * backend's mock endpoint in dev). Our servers never handle the video bytes.
 * XMLHttpRequest instead of fetch: it reports upload progress.
 */
export function uploadDirect(
  url: string,
  fields: Record<string, string>,
  file: File,
  onProgress: (percent: number) => void,
): { promise: Promise<void>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<void>((resolve, reject) => {
    const form = new FormData();
    for (const [key, value] of Object.entries(fields)) form.append(key, value);
    form.append("file", file); // must be the LAST field for S3 POST uploads
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)));
    };
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`HTTP ${xhr.status}`)));
    xhr.onerror = () => reject(new Error("network"));
    xhr.onabort = () => reject(new Error("aborted"));
    xhr.open("POST", url);
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
