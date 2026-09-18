## Module <om_hr_payroll_account>

#### 17.09.2026
#### Version 1.2.0
##### ADD
- register the payment of a payslip or of a whole batch, with a payment status on the payslip
- the accounts of a salary rule are set per company: the rules shared by the companies keep their own
  accounts in each of them, and the entry of a payslip uses the accounts of its company
##### FIX
- confirming a payslip of another company no longer fails on the accounts of a shared salary rule

#### 16.09.2026
#### Version 1.1.0
##### ADD
- a salary journal on the payslip batches: the payslips of a batch are posted in it
##### FIX
- the payroll officers without accounting rights can confirm a payslip
- the salary journal of a payslip must belong to the company of the payslip
- cancelling a payslip deletes its entry, unless the period is locked or the entry is reconciled

#### 14.09.2026
#### Version 1.0.0
##### ADD
- initial release for Odoo 20 Community

#### 08.02.2026
#### Version 19.0.0.0
##### ADD
- initial release for Odoo 19 Community

#### 09.12.2023
#### Version 18.0.1.0.0
##### ADD
- initial release
