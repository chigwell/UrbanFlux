export function abortError() {
  return new DOMException("Auto improvement aborted", "AbortError");
}

export function throwIfAborted(signal) {
  if (signal?.aborted) {
    throw abortError();
  }
}

export function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }

    const timer = window.setTimeout(resolve, ms);

    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(abortError());
      },
      { once: true },
    );
  });
}
