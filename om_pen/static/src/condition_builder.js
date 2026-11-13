import { Component } from "@odoo/owl";

/**
 * Operators offered per field type. The value side changes with the operator: `set`
 * and `not set` take none, `in` takes a comma separated list, the rest take one value.
 */
const OPERATORS = {
    common: [
        { op: "=", label: "is" },
        { op: "!=", label: "is not" },
        { op: "set", label: "is set" },
        { op: "not set", label: "is not set" },
    ],
    number: [
        { op: ">", label: "is more than" },
        { op: "<", label: "is less than" },
        { op: ">=", label: "is at least" },
        { op: "<=", label: "is at most" },
    ],
    text: [{ op: "in", label: "is one of" }],
    selection: [{ op: "in", label: "is one of" }],
};

const NUMERIC = ["integer", "float", "monetary"];
const TEXTUAL = ["char", "text", "html"];

/** Quote a value the way the expression needs it. */
function literal(value, type) {
    if (NUMERIC.includes(type)) {
        return String(Number(value) || 0);
    }
    if (type === "boolean") {
        return value === "true" || value === true ? "True" : "False";
    }
    return JSON.stringify(String(value ?? ""));
}

/** Build the python expression the view actually carries. */
export function buildExpression(condition, fields) {
    const rows = (condition?.rows || []).filter((row) => row.field && row.operator);
    if (!rows.length) {
        return "";
    }
    const join = condition.join === "or" ? " or " : " and ";
    return rows
        .map((row) => {
            const type = fields[row.field]?.type;
            if (row.operator === "set") {
                return `${row.field}`;
            }
            if (row.operator === "not set") {
                return `not ${row.field}`;
            }
            if (row.operator === "in") {
                const items = String(row.value || "")
                    .split(",")
                    .map((item) => literal(item.trim(), type))
                    .join(", ");
                return `${row.field} in [${items}]`;
            }
            // "is" is stored as "=", which in python would be an assignment
            const operator = row.operator === "=" ? "==" : row.operator;
            return `${row.field} ${operator} ${literal(row.value, type)}`;
        })
        .join(join);
}

export class ConditionBuilder extends Component {
    static template = "om_pen.ConditionBuilder";
    static props = {
        condition: { type: Object },
        fields: { type: Object },
        fieldNames: { type: Array },
    };

    operatorsFor(fieldName) {
        const type = this.props.fields[fieldName]?.type;
        let operators = [...OPERATORS.common];
        if (NUMERIC.includes(type)) {
            operators = operators.concat(OPERATORS.number);
        }
        if (TEXTUAL.includes(type) || type === "selection") {
            operators = operators.concat(OPERATORS.text);
        }
        return operators;
    }

    needsValue(row) {
        return !["set", "not set"].includes(row.operator);
    }

    selectionOf(fieldName) {
        return this.props.fields[fieldName]?.selection || [];
    }

    typeOf(fieldName) {
        return this.props.fields[fieldName]?.type;
    }

    addRow() {
        this.props.condition.rows.push({ field: "", operator: "=", value: "" });
    }

    removeRow(index) {
        this.props.condition.rows.splice(index, 1);
    }

    onFieldChange(row) {
        // the operators on offer depend on the type, so a stale one must not linger
        const allowed = this.operatorsFor(row.field).map((entry) => entry.op);
        if (!allowed.includes(row.operator)) {
            row.operator = "=";
        }
        row.value = "";
    }
}
