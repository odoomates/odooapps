from odoo import api, fields, models
from odoo.tools import SQL


class HrPayslipAnalysis(models.Model):
    """ The payslip lines, one per salary rule of a payslip, with the employee, the department and the job of the
    contract the payslip was computed on. The lines of the refunds are counted negative. """
    _name = 'hr.payslip.analysis'
    _description = 'Payroll Analysis'
    _auto = False
    _rec_name = 'slip_id'
    _order = 'date desc, slip_id desc, sequence'
    _depends = {
        'hr.payslip': [
            'number', 'date_from', 'date_to', 'state', 'credit_note', 'company_id', 'struct_id',
            'payslip_run_id', 'employee_id', 'version_id',
        ],
        'hr.payslip.line': [
            'slip_id', 'salary_rule_id', 'category_id', 'code', 'sequence', 'quantity',
            'amount', 'rate', 'total',
        ],
        'hr.version': ['department_id', 'job_id'],
    }

    slip_id = fields.Many2one('hr.payslip', 'Payslip', readonly=True)
    number = fields.Char('Reference', readonly=True)
    date_from = fields.Date('Period Start', readonly=True)
    date = fields.Date('Period End', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Done'),
        ('cancel', 'Rejected'),
    ], readonly=True)
    credit_note = fields.Boolean('Refund', readonly=True)
    employee_id = fields.Many2one('hr.employee', 'Employee', readonly=True)
    department_id = fields.Many2one('hr.department', 'Department', readonly=True)
    job_id = fields.Many2one('hr.job', 'Job Position', readonly=True)
    struct_id = fields.Many2one('hr.payroll.structure', 'Structure', readonly=True)
    payslip_run_id = fields.Many2one('hr.payslip.run', 'Batch', readonly=True)
    company_id = fields.Many2one('res.company', 'Company', readonly=True)
    salary_rule_id = fields.Many2one('hr.salary.rule', 'Rule', readonly=True)
    category_id = fields.Many2one('hr.salary.rule.category', 'Category', readonly=True)
    code = fields.Char(readonly=True)
    sequence = fields.Integer(readonly=True)
    quantity = fields.Float(readonly=True, aggregator=None)
    rate = fields.Float('Rate (%)', readonly=True, aggregator=None)
    amount = fields.Float(readonly=True, aggregator=None)
    total = fields.Float(readonly=True)
    employee_count = fields.Integer('# Employees', readonly=True, aggregator='count_distinct')

    @api.model
    def init(self):
        self.env.cr.execute(SQL("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    line.id AS id,
                    slip.id AS slip_id,
                    slip.number AS number,
                    slip.date_from AS date_from,
                    slip.date_to AS date,
                    slip.state AS state,
                    COALESCE(slip.credit_note, FALSE) AS credit_note,
                    slip.employee_id AS employee_id,
                    version.department_id AS department_id,
                    version.job_id AS job_id,
                    slip.struct_id AS struct_id,
                    slip.payslip_run_id AS payslip_run_id,
                    slip.company_id AS company_id,
                    line.salary_rule_id AS salary_rule_id,
                    line.category_id AS category_id,
                    line.code AS code,
                    line.sequence AS sequence,
                    line.quantity AS quantity,
                    line.rate AS rate,
                    line.amount AS amount,
                    CASE WHEN slip.credit_note THEN -line.total ELSE line.total END AS total,
                    slip.employee_id AS employee_count
                FROM hr_payslip_line line
                JOIN hr_payslip slip ON slip.id = line.slip_id
                LEFT JOIN hr_version version ON version.id = slip.version_id
            )""", SQL.identifier(self._table)))
