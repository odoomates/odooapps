import { evaluateExpr } from "@web/core/py_js/py";
import { exprToBoolean } from "@web/core/utils/strings";
import { createElement } from "@web/core/utils/xml";
import { stringToOrderBy } from "@web/search/utils/order_by";
import { Field } from "@web/views/fields/field";
import { DEFAULT_PRECISION, GANTT_SCALES } from "./gantt_helpers";

export const POPOVER_TEMPLATE = "gantt-popover";

export class GanttParseArchError extends Error {}

function parseDict(xmlDoc, attribute) {
    const value = xmlDoc.getAttribute(attribute);
    if (!value) {
        return {};
    }
    const result = evaluateExpr(value);
    if (!result || typeof result !== "object") {
        throw new GanttParseArchError(`Gantt attribute "${attribute}" must be a dictionary.`);
    }
    return result;
}

export class GanttArchParser {
    parse(xmlDoc, models, modelName) {
        const fields = models[modelName].fields;
        const jsClass = xmlDoc.getAttribute("js_class") || null;
        const fieldNames = new Set(fields.display_name ? ["display_name"] : []);

        const dateStartField = xmlDoc.getAttribute("date_start");
        const dateStopField = xmlDoc.getAttribute("date_stop");
        if (!dateStartField || !dateStopField) {
            throw new GanttParseArchError(
                `Gantt view must define "date_start" and "date_stop" attributes.`
            );
        }
        const fieldAttributes = {
            colorField: xmlDoc.getAttribute("color"),
            progressField: xmlDoc.getAttribute("progress"),
            consolidationField: xmlDoc.getAttribute("consolidation"),
            dependencyField: xmlDoc.getAttribute("dependency_field"),
        };
        for (const fieldName of [dateStartField, dateStopField, ...Object.values(fieldAttributes)]) {
            if (fieldName) {
                if (!(fieldName in fields)) {
                    throw new GanttParseArchError(
                        `Field "${fieldName}" of the gantt view does not exist on ${modelName}.`
                    );
                }
                fieldNames.add(fieldName);
            }
        }

        let scales = [...GANTT_SCALES];
        if (xmlDoc.getAttribute("scales")) {
            scales = xmlDoc
                .getAttribute("scales")
                .split(",")
                .map((scale) => scale.trim())
                .filter((scale) => GANTT_SCALES.includes(scale));
        }
        if (!scales.length) {
            scales = [...GANTT_SCALES];
        }
        let defaultScale = xmlDoc.getAttribute("default_scale");
        if (!scales.includes(defaultScale)) {
            defaultScale = scales.includes("month") ? "month" : scales[0];
        }
        const precision = { ...DEFAULT_PRECISION, ...parseDict(xmlDoc, "precision") };

        // decoration-xxx="python expression" on the pills
        const decorations = [];
        for (const name of xmlDoc.getAttributeNames()) {
            if (name.startsWith("decoration-")) {
                const condition = xmlDoc.getAttribute(name);
                decorations.push({ name: name.slice("decoration-".length), condition });
                for (const word of condition.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []) {
                    if (word in fields) {
                        fieldNames.add(word);
                    }
                }
            }
        }
        const progressBarFields = (xmlDoc.getAttribute("progress_bar") || "")
            .split(",")
            .map((name) => name.trim())
            .filter((name) => name && name in fields);

        const defaultGroupBy = (xmlDoc.getAttribute("default_group_by") || "")
            .split(",")
            .map((name) => name.trim())
            .filter(Boolean);

        // popover: a "gantt-popover" template, or popover-header/body/footer templates
        const popoverNode = createElement("popover");
        const popoverTemplates = createElement("templates");
        popoverNode.appendChild(popoverTemplates);
        const popoverFieldNodes = {};
        for (const child of xmlDoc.children) {
            if (child.tagName === "field") {
                const fieldInfo = Field.parseFieldNode(child, models, modelName, "gantt", jsClass);
                popoverFieldNodes[fieldInfo.name] = fieldInfo;
                fieldNames.add(fieldInfo.name);
                popoverNode.insertBefore(
                    createElement("field", { name: fieldInfo.name }),
                    popoverTemplates
                );
            } else if (child.tagName === "templates") {
                for (const template of [...child.children]) {
                    const name = template.getAttribute("t-name");
                    const clone = template.cloneNode(true);
                    if (name === POPOVER_TEMPLATE) {
                        clone.setAttribute("t-name", "popover-body");
                    }
                    if (["popover-body", "popover-header", "popover-footer"].includes(clone.getAttribute("t-name"))) {
                        popoverTemplates.appendChild(clone);
                    }
                }
            }
        }

        const hasTemplate = (name) =>
            [...popoverTemplates.children].some((node) => node.getAttribute("t-name") === name);
        if (hasTemplate("popover-body") && !hasTemplate("popover-header")) {
            const header = createElement("t", { "t-name": "popover-header" }, [
                createElement("field", { name: "display_name" }),
            ]);
            popoverTemplates.appendChild(header);
        }

        return {
            activeActions: {
                create: exprToBoolean(xmlDoc.getAttribute("create"), true),
                edit: exprToBoolean(xmlDoc.getAttribute("edit"), true),
                delete: exprToBoolean(xmlDoc.getAttribute("delete"), true),
                plan: exprToBoolean(xmlDoc.getAttribute("plan"), true),
            },
            string: xmlDoc.getAttribute("string") || "",
            dateStartField,
            dateStopField,
            ...fieldAttributes,
            consolidationMax: parseDict(xmlDoc, "consolidation_max"),
            thumbnails: parseDict(xmlDoc, "thumbnails"),
            emptyRowLabels: parseDict(xmlDoc, "empty_row_labels"),
            decorations,
            progressBarFields,
            precision,
            scales,
            defaultScale,
            defaultGroupBy,
            defaultOrder: stringToOrderBy(xmlDoc.getAttribute("default_order") || null),
            totalRow: exprToBoolean(xmlDoc.getAttribute("total_row"), false),
            displayUnavailability: exprToBoolean(xmlDoc.getAttribute("display_unavailability"), false),
            pillLabel: exprToBoolean(xmlDoc.getAttribute("pill_label"), false),
            formViewId: parseInt(xmlDoc.getAttribute("form_view_id"), 10) || false,
            fieldNames: [...fieldNames],
            popoverNode,
            popoverFieldNodes,
        };
    }
}
