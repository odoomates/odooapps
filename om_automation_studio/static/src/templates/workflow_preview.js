/** @odoo-module **/

import { Component } from "@odoo/owl";

import { NODE_TYPES, edgePath, inPoint, nodeHeight, portPoint, portsOf } from "../designer/designer";

const NODE_W = 216;
const MARGIN = 24;
// what fits on a step of the preview
const LABEL_SIZE = 20;
// drawn at this scale, readable; a wider chart scrolls
const SCALE = 0.6;

/** A chart drawn small and read-only: the preview of a template. */
export class WorkflowPreview extends Component {
    static template = "om_automation_studio.Preview";
    static props = { graph: Object, issues: { type: Array, optional: true } };
    static defaultProps = { issues: [] };

    setup() {
        this.NODE_TYPES = NODE_TYPES;
        this.NODE_W = NODE_W;
        this.nodeHeight = nodeHeight;
    }

    get nodes() {
        return this.props.graph.nodes || [];
    }

    box() {
        const nodes = this.nodes;
        if (!nodes.length) {
            return { x: 0, y: 0, width: 100, height: 100 };
        }
        const x = Math.min(...nodes.map((node) => node.x)) - MARGIN;
        const y = Math.min(...nodes.map((node) => node.y)) - MARGIN;
        const maxX = Math.max(...nodes.map((node) => node.x + NODE_W)) + MARGIN;
        const maxY = Math.max(...nodes.map((node) => node.y + nodeHeight(node))) + MARGIN;
        return { x, y, width: maxX - x, height: maxY - y };
    }

    viewBox() {
        const { x, y, width, height } = this.box();
        return `${x} ${y} ${width} ${height}`;
    }

    width() {
        return Math.round(this.box().width * SCALE);
    }

    height() {
        return Math.round(this.box().height * SCALE);
    }

    edges() {
        const byId = Object.fromEntries(this.nodes.map((node) => [node.id, node]));
        return (this.props.graph.edges || [])
            .map((edge) => {
                const source = byId[edge.source];
                const target = byId[edge.target];
                if (!source || !target || !portsOf(source).includes(edge.port)) {
                    return null;
                }
                return { id: edge.id, d: edgePath(portPoint(source, edge.port), inPoint(target)) };
            })
            .filter(Boolean);
    }

    hasError(node) {
        return this.props.issues.some((issue) => issue.node === node.id && issue.level === "error");
    }

    label(node) {
        const label = node.label || "";
        return label.length > LABEL_SIZE ? `${label.slice(0, LABEL_SIZE - 1)}…` : label;
    }
}
