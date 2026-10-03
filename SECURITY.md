# Security Policy

## Supported versions

Security problems can be reported for **every version** of the modules, from
10.0 to 20.0. Each version is a branch of this repository.

## Reporting a vulnerability

**Do not open a public issue, pull request or discussion for a security
problem.** Write to **odoomates@gmail.com** with the subject
`[SECURITY] <module name>`.

Please give:

- the module and the Odoo version (branch), and the commit if you know it;
- what the problem is, and what an attacker could do with it (for example:
  read the records of another company, run code, bypass an access right);
- the steps to reproduce it, on a fresh database if you can;
- a patch, if you have one.

Do not test on a database holding real customer data, and do not access, change
or delete data that is not yours.

## What happens next

1. We acknowledge your report, usually within 10 days.
2. We confirm the problem and work on a fix with you. We may ask you questions.
3. The fix is committed to every affected version.
4. Once the fix is published, we credit you in the commit, unless you ask us
   not to.

Please give us reasonable time to publish the fix before you disclose the
problem publicly.

## Out of scope

- Problems of Odoo itself (community or enterprise): report them to Odoo S.A. at
  <https://www.odoo.com/security-report>.
- Problems that need administrator rights, or a modified Odoo server, to exploit.
