/* Live tracking page of a field service visit: polls the status, arrival time and position of
 * the technician, and shows them on an OpenStreetMap map (Leaflet). Plain script, loaded by the
 * page itself. */
/* global L */
(function () {
    "use strict";

    const REFRESH_MS = 30000;
    const card = document.querySelector(".o_fs_track_card");
    if (!card) {
        return;
    }
    const token = card.dataset.token;
    const mapEl = document.getElementById("o_fs_track_map");
    let map = null;
    let technicianMarker = null;

    function setText(selector, text) {
        const el = document.querySelector(selector);
        if (el) {
            el.textContent = text || "";
        }
    }

    function toggle(selector, visible) {
        const el = document.querySelector(selector);
        if (el) {
            el.classList.toggle("d-none", !visible);
        }
    }

    function initMap() {
        const lat = parseFloat(mapEl && mapEl.dataset.siteLat);
        const lng = parseFloat(mapEl && mapEl.dataset.siteLng);
        if (!mapEl || typeof L === "undefined" || isNaN(lat) || isNaN(lng)) {
            return;
        }
        map = L.map(mapEl, { scrollWheelZoom: false }).setView([lat, lng], 14);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);
        L.circleMarker([lat, lng], { radius: 9, color: "#714B67", fillColor: "#714B67", fillOpacity: 0.9 }).addTo(map);
    }

    function showPosition(position, site) {
        if (!map) {
            return;
        }
        if (!position) {
            if (technicianMarker) {
                map.removeLayer(technicianMarker);
                technicianMarker = null;
            }
            return;
        }
        const point = [position.lat, position.lng];
        if (technicianMarker) {
            technicianMarker.setLatLng(point);
        } else {
            technicianMarker = L.circleMarker(point, {
                radius: 9,
                color: "#059669",
                fillColor: "#059669",
                fillOpacity: 0.9,
            }).addTo(map);
        }
        if (site) {
            map.fitBounds([point, [site.lat, site.lng]], { padding: [40, 40], maxZoom: 15 });
        }
    }

    function render(data) {
        if (data.expired) {
            window.location.reload();
            return;
        }
        setText(".o_fs_track_technician", data.technician || "-");
        setText(".o_fs_track_eta", data.eta);
        toggle(".o_fs_track_eta", Boolean(data.eta));
        setText(".o_fs_track_updated", data.updated);
        toggle(".o_fs_track_updated_box", Boolean(data.updated));
        let reached = true;
        for (const step of document.querySelectorAll(".o_fs_track_step")) {
            step.classList.toggle("o_fs_track_step_done", reached);
            step.classList.toggle("o_fs_track_step_current", step.dataset.step === data.step);
            if (step.dataset.step === data.step) {
                reached = false;
            }
        }
        showPosition(data.position, data.site);
    }

    async function refresh() {
        try {
            const response = await fetch(`/field-service/track/${encodeURIComponent(token)}/data`, {
                credentials: "same-origin",
            });
            if (response.ok) {
                render(await response.json());
            }
        } catch {
            // offline: try again at the next refresh
        }
    }

    initMap();
    refresh();
    window.setInterval(refresh, REFRESH_MS);
})();
