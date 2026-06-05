"use client";

import { useEffect, useState } from "react";

export default function Home() {
  const [message, setMessage] = useState("Loading...");

  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

    fetch(`${apiUrl}/hello`)
      .then((res) => res.json())
      .then((data) => setMessage(data.message || "No message"))
      .catch(() => setMessage("Unable to reach backend"));
  }, []);

  return (
    <main className="container">
      <h1>UrbanFlux Frontend</h1>
      <p>{message}</p>
    </main>
  );
}
