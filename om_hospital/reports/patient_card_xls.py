from odoo import models


# Creating Excel Report
# https://www.youtube.com/watch?v=cCyMy2kxxZs&list=PLqRRLx0cl0hoJhjFWkFYowveq2Zn55dhM&index=46
class PatientCardXLS(models.AbstractModel):
    _name = 'report.om_hospital.report_patient_xls'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, lines):
        format1 = workbook.add_format({'font_size': 14, 'align': 'vcenter', 'bold': True})
        format2 = workbook.add_format({'font_size': 10, 'align': 'vcenter', })
        sheet = workbook.add_worksheet('Patient Card')

        sheet.right_to_left()
        
        sheet.set_column(3, 3, 50)
        sheet.set_column(2, 2, 30)
        sheet.write(2, 2, 'Name', format1)
        sheet.write(2, 3, lines.patient_name, format2)
        sheet.write(3, 2, 'Age', format1)
        sheet.write(3, 3, lines.patient_age, format2)
