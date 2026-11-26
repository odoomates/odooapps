import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal, useProps } from "@odoo/owl";
import { loadCSS, loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const LEAFLET = "/om_field_service/static/lib/leaflet";

export const STATE_COLORS = {
    new: "#8F8F8F",
    planned: "#71639E",
    travelling: "#0284C7",
    in_progress: "#E9A23B",
    waiting_parts: "#DC6965",
    done: "#059669",
    cancelled: "#BDBDBD",
};

/**
 * Map of the jobs (OpenStreetMap tiles drawn with Leaflet): a marker per site, coloured by
 * status, with the route of a technician in the order of their jobs.
 */
export class FieldServiceMap extends Component {
    static template = "om_field_service.JobMap";
    props = useProps({ ...standardActionServiceProps });

    mapRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.colors = STATE_COLORS;
        const params = this.props.action.params || {};
        this.jobIds = params.job_ids || null;
        this.periods = [
            ["today", _t("Today")],
            ["tomorrow", _t("Tomorrow")],
            ["week", _t("Next 7 days")],
            ["open", _t("All open jobs")],
        ];
        this.state = proxy({
            period: "today",
            employeeId: false,
            jobs: [],
            technicians: [],
            selectedId: null,
        });
        this.markers = {};
        onWillStart(async () => {
            await Promise.all([
                loadCSS(`${LEAFLET}/leaflet.css`),
                loadJS(`${LEAFLET}/leaflet.js`),
                this.load(),
            ]);
        });
        onMounted(() => this.renderMap());
        onWillUnmount(() => this.map && this.map.remove());
    }

    async load() {
        const data = await this.orm.call("project.task", "fs_map_data", [
            this.state.period,
            this.state.employeeId,
            this.jobIds,
        ]);
        this.state.jobs = data.jobs;
        this.state.technicians = data.technicians;
    }

    get locatedJobs() {
        return this.state.jobs.filter((job) => job.lat || job.lng);
    }

    get unlocatedJobs() {
        return this.state.jobs.filter((job) => !job.lat && !job.lng);
    }

    get routeUrl() {
        const jobs = this.locatedJobs.filter((job) => job.start);
        if (!this.state.employeeId || jobs.length < 1) {
            return false;
        }
        return "https://www.google.com/maps/dir/" + jobs.map((job) => `${job.lat},${job.lng}`).join("/");
    }

    renderMap() {
        const L = window.L;
        if (!this.map) {
            this.map = L.map(this.mapRef(), { zoomControl: true });
            L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
                maxZoom: 19,
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            }).addTo(this.map);
            this.layer = L.layerGroup().addTo(this.map);
        }
        this.layer.clearLayers();
        this.markers = {};
        const points = [];
        for (const job of this.locatedJobs) {
            const point = [job.lat, job.lng];
            points.push(point);
            const marker = L.circleMarker(point, {
                radius: 10,
                weight: 3,
                color: "#FFFFFF",
                fillColor: this.colors[job.state] || "#714B67",
                fillOpacity: 0.95,
            });
            marker.bindPopup(() => this.popupContent(job));
            marker.bindTooltip(job.number || job.name);
            marker.on("click", () => (this.state.selectedId = job.id));
            marker.addTo(this.layer);
            this.markers[job.id] = marker;
        }
        if (this.state.employeeId) {
            const route = this.locatedJobs.filter((job) => job.start).map((job) => [job.lat, job.lng]);
            if (route.length > 1) {
                L.polyline(route, { color: "#714B67", weight: 3, dashArray: "6 6" }).addTo(this.layer);
            }
        }
        if (points.length) {
            this.map.fitBounds(L.latLngBounds(points).pad(0.2), { maxZoom: 15 });
        } else {
            this.map.setView([20, 0], 2);
        }
    }

    popupContent(job) {
        const root = document.createElement("div");
        root.className = "o_fs_map_popup";
        const add = (tag, text, className) => {
            const el = document.createElement(tag);
            el.textContent = text;
            if (className) {
                el.className = className;
            }
            root.appendChild(el);
            return el;
        };
        add("div", job.number, "small text-muted");
        add("div", job.name, "fw-bold");
        add("div", job.customer);
        add("div", job.address, "small");
        if (job.start) {
            add("div", this.formatTime(job), "small");
        }
        if (job.technicians) {
            add("div", job.technicians, "small text-muted");
        }
        add("div", job.state_label, "small fw-bold").style.color = this.colors[job.state] || "";
        const links = document.createElement("div");
        links.className = "d-flex gap-2 mt-1";
        const open = document.createElement("a");
        open.href = "#";
        open.textContent = _t("Open");
        open.addEventListener("click", (ev) => {
            ev.preventDefault();
            this.openJob(job);
        });
        links.appendChild(open);
        if (job.directions) {
            const directions = document.createElement("a");
            directions.href = job.directions;
            directions.target = "_blank";
            directions.rel = "noopener";
            directions.textContent = _t("Directions");
            links.appendChild(directions);
        }
        root.appendChild(links);
        return root;
    }

    formatTime(job) {
        const start = luxon.DateTime.fromSQL(job.start, { zone: "utc" }).toLocal();
        const end = job.end ? luxon.DateTime.fromSQL(job.end, { zone: "utc" }).toLocal() : null;
        const day = start.toLocaleString({ weekday: "short", day: "numeric", month: "short" });
        const from = start.toLocaleString(luxon.DateTime.TIME_SIMPLE);
        return end ? `${day} ${from} - ${end.toLocaleString(luxon.DateTime.TIME_SIMPLE)}` : `${day} ${from}`;
    }

    async setPeriod(period) {
        this.state.period = period;
        this.jobIds = null;
        await this.load();
        this.renderMap();
    }

    async setEmployee(ev) {
        this.state.employeeId = Number(ev.target.value) || false;
        this.jobIds = null;
        await this.load();
        this.renderMap();
    }

    focusJob(job) {
        this.state.selectedId = job.id;
        const marker = this.markers[job.id];
        if (marker) {
            this.map.setView(marker.getLatLng(), Math.max(this.map.getZoom(), 15));
            marker.openPopup();
        }
    }

    openJob(job) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: job.id,
            views: [[false, "form"]],
            context: { form_view_ref: "om_field_service.project_task_view_form_fs", om_fs_job: true },
        });
    }
}

registry.category("actions").add("om_fs_map", FieldServiceMap);
