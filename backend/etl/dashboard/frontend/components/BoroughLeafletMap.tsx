"use client";

import { useEffect, useRef } from "react";
import * as L from "leaflet";

type BoroughPolygon = {
  boroughName: string;
  rings: [number, number][][];
  color: string;
};

type BoroughLeafletMapProps = {
  polygons: BoroughPolygon[];
  bounds: [[number, number], [number, number]];
  selectedBoroughName?: string | null;
  onBoroughClick?: (boroughName: string) => void;
};

export default function BoroughLeafletMap({
  polygons,
  bounds,
  selectedBoroughName,
  onBoroughClick,
}: BoroughLeafletMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const polygonLayerRef = useRef<L.Polygon[]>([]);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = L.map(mapContainerRef.current, {
      scrollWheelZoom: true,
      zoomControl: true,
    });
    tileLayerRef.current = L.tileLayer(
      "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      },
    ).addTo(map);
    mapRef.current = map;

    return () => {
      polygonLayerRef.current.forEach((polygon) => polygon.remove());
      polygonLayerRef.current = [];
      tileLayerRef.current?.remove();
      tileLayerRef.current = null;
      mapRef.current?.off();
      mapRef.current?.remove();
      mapRef.current = null;
      const container = mapContainerRef.current;
      if (container) {
        (container as { _leaflet_id?: unknown })._leaflet_id = undefined;
      }
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;

    polygonLayerRef.current.forEach((polygon) => {
      polygon.remove();
    });
    polygonLayerRef.current = [];

    polygons.forEach((boundary) => {
      boundary.rings.forEach((ring) => {
        const isSelected = boundary.boroughName === selectedBoroughName;
        const polygon = L.polygon(ring, {
          color: boundary.color,
          weight: isSelected ? 2.6 : 1.2,
          fillColor: boundary.color,
          fillOpacity: isSelected ? 0.42 : 0.22,
        }).addTo(mapRef.current as L.Map);
        polygon.bindTooltip(`${boundary.boroughName}`, { direction: "top", sticky: true });
        polygon.on("click", () => onBoroughClick?.(boundary.boroughName));
        polygonLayerRef.current.push(polygon);
      });
    });

    mapRef.current.fitBounds(bounds, { padding: [26, 26] });
  }, [bounds, onBoroughClick, polygons, selectedBoroughName]);

  return <div className="borough-map" ref={mapContainerRef} />;
}
