import { useEffect, useRef } from "react";

// Uses Leaflet + free OpenStreetMap tiles (no API key needed). Shows the
// booking address as a fixed pin and the artist's last-known location as
// a second marker, zoomed to fit both.
export default function LiveMap({ destLat, destLng, currentLat, currentLng }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const destMarkerRef = useRef(null);
  const currentMarkerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    import("leaflet").then((L) => {
      if (cancelled || !containerRef.current) return;

      if (!mapRef.current) {
        mapRef.current = L.map(containerRef.current, { zoomControl: false, attributionControl: false });
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 }).addTo(mapRef.current);

        const destIcon = L.divIcon({
          className: "",
          html: '<div style="background:#6b1d2c;width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 0 0 2px #6b1d2c33"></div>',
          iconSize: [14, 14],
        });
        destMarkerRef.current = L.marker([destLat, destLng], { icon: destIcon }).addTo(mapRef.current);
      }

      const map = mapRef.current;

      if (currentLat != null && currentLng != null) {
        const artistIcon = L.divIcon({
          className: "",
          html: '<div style="background:#c9a227;width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 0 0 3px #c9a22744"></div>',
          iconSize: [16, 16],
        });
        if (currentMarkerRef.current) {
          currentMarkerRef.current.setLatLng([currentLat, currentLng]);
        } else {
          currentMarkerRef.current = L.marker([currentLat, currentLng], { icon: artistIcon }).addTo(map);
        }
        map.fitBounds(
          [
            [destLat, destLng],
            [currentLat, currentLng],
          ],
          { padding: [30, 30], maxZoom: 15 }
        );
      } else {
        map.setView([destLat, destLng], 13);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [destLat, destLng, currentLat, currentLng]);

  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
  }, []);

  return <div ref={containerRef} className="h-48 w-full rounded-xl border border-line overflow-hidden" />;
}
