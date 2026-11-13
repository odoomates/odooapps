""" The accounting workflows offered among the templates of Automation Studio. Each builder gives the name, the
description and the chart of a template, drawn with the helpers of the generic templates. """
from odoo.addons.om_automation_studio.tools.templates import activity, chain, e, n

BILL = [('move_type', '=', 'in_invoice')]
INVOICE = [('move_type', '=', 'out_invoice')]
UNPAID = [('payment_state', 'in', ['not_paid', 'partial'])]
PAID = [('payment_state', 'in', ['paid', 'in_payment', 'reversed'])]
CREATOR = {'mode': 'field', 'field': 'create_uid'}
SALESPERSON = {'mode': 'field', 'field': 'invoice_user_id'}


def _manager(env):
    """ The administrator, to be replaced by the accounting manager of the company in the designer. """
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    return {'mode': 'user', 'id': admin.id if admin else env.uid}


def bill_due_soon(env):
    _ = env._
    nodes = [
        n('start', 'start', 0, 0, _("3 days before the due date"), trigger='date', date_field='invoice_date_due',
          amount=3, unit='days', direction='before', domain=repr(BILL + [('state', '=', 'posted')] + UNPAID),
          policy='single', stop_domain=repr(PAID)),
        activity(env, 'pay', 1, 0, _("Pay the bill"), CREATOR, _("Pay {{ object.display_name }}, due in 3 days")),
        n('end', 'end', 2, 0, ''),
    ]
    return (_("Bills: Due Soon"),
            _("Three days before the due date of a posted vendor bill not paid yet, an activity to pay it."),
            {'nodes': nodes, 'edges': chain(nodes)})


def bill_left_in_draft(env):
    _ = env._
    nodes = [
        n('start', 'start', 0, 0, _("3 days in draft"), trigger='date', date_field='create_date', amount=3,
          unit='days', direction='after', domain=repr(BILL + [('state', '=', 'draft')]), policy='single',
          stop_domain=repr([('state', '!=', 'draft')])),
        activity(env, 'check', 1, 0, _("Check and post"), CREATOR,
                 _("Check and post {{ object.display_name }}, in draft for 3 days")),
        n('end', 'end', 2, 0, ''),
    ]
    return (_("Bills: Left in Draft"),
            _("A vendor bill still in draft 3 days after it was created: an activity to check and post it."),
            {'nodes': nodes, 'edges': chain(nodes)})


def bill_without_reference(env):
    _ = env._
    nodes = [
        n('start', 'start', 0, 0, _("Posted without reference"), trigger='change', fields=['state'],
          domain=repr(BILL + [('state', '=', 'posted'), ('ref', '=', False)]), becomes=True, policy='single'),
        n('note', 'note', 1, 0, _("Note"),
          body=_("Posted without the reference of the vendor: add it, so that a bill entered twice is found.")),
        activity(env, 'add', 2, 0, _("Add the reference"), CREATOR,
                 _("Add the vendor reference of {{ object.display_name }}")),
        n('end', 'end', 3, 0, ''),
    ]
    return (_("Bills: Posted Without Vendor Reference"),
            _("A vendor bill posted without the reference of the vendor: a note and an activity to add it, so "
              "that the duplicates are found."),
            {'nodes': nodes, 'edges': chain(nodes)})


def invoice_not_sent(env):
    _ = env._
    start = n('start', 'start', 0, 0, _("Invoice posted"), trigger='change', fields=['state'],
              domain=repr(INVOICE + [('state', '=', 'posted')]), becomes=True, policy='single')
    wait = n('wait', 'wait', 1, 0, _("1 day later"), mode='duration', amount=1, unit='days')
    check = n('sent', 'condition', 2, 0, _("Not sent yet?"),
              domain=repr([('is_move_sent', '=', False), ('state', '=', 'posted')]))
    send = activity(env, 'send', 3, -1, _("Send it"), SALESPERSON,
                    _("Send {{ object.display_name }} to the customer"))
    end = n('end', 'end', 4, 0, '')
    edges = chain([start, wait, check]) + [e('sent', 'yes', 'send'), e('sent', 'no', 'end'), e('send', 'out', 'end')]
    return (_("Invoices: Posted but Not Sent"),
            _("A customer invoice posted and still not sent the next day: an activity for the salesperson to "
              "send it."),
            {'nodes': [start, wait, check, send, end], 'edges': edges})


def invoice_large(env):
    _ = env._
    nodes = [
        n('start', 'start', 0, 0, _("Large invoice posted"), trigger='change', fields=['state'],
          domain=repr(INVOICE + [('state', '=', 'posted'), ('amount_total_signed', '>=', 10000)]), becomes=True,
          policy='single'),
        activity(env, 'follow', 1, 0, _("Follow its payment"), _manager(env),
                 _("{{ object.display_name }} of {{ object.amount_total }} posted: follow its payment")),
        n('end', 'end', 2, 0, ''),
    ]
    return (_("Invoices: Large Amount Posted"),
            _("A customer invoice of 10,000 or more is posted: an activity for the accounting manager to follow "
              "its payment. Choose the manager and the amount in the designer."),
            {'nodes': nodes, 'edges': chain(nodes)})


def payment_left_in_draft(env):
    _ = env._
    nodes = [
        n('start', 'start', 0, 0, _("2 days in draft"), trigger='date', date_field='create_date', amount=2,
          unit='days', direction='after', domain=repr([('state', '=', 'draft')]), policy='single',
          stop_domain=repr([('state', '!=', 'draft')])),
        activity(env, 'confirm', 1, 0, _("Confirm or cancel"), CREATOR,
                 _("Confirm or cancel {{ object.display_name }}, in draft for 2 days")),
        n('end', 'end', 2, 0, ''),
    ]
    return (_("Payments: Left in Draft"),
            _("A payment still in draft 2 days after it was created: an activity to confirm or cancel it."),
            {'nodes': nodes, 'edges': chain(nodes)})


def cheque_maturing(env):
    _ = env._
    nodes = [
        n('start', 'start', 0, 0, _("1 day before the cheque date"), trigger='date', date_field='cheque_date',
          amount=1, unit='days', direction='before',
          domain=repr([('pdc_type', '=', 'receive'), ('state', '=', 'registered')]), policy='single',
          stop_domain=repr([('state', '!=', 'registered')])),
        activity(env, 'deposit', 1, 0, _("Deposit it"), CREATOR,
                 _("Deposit the cheque {{ object.display_name }}, dated tomorrow")),
        n('end', 'end', 2, 0, ''),
    ]
    return (_("Post-dated Cheques: Maturing"),
            _("The day before the date of a cheque received and registered: an activity to deposit it."),
            {'nodes': nodes, 'edges': chain(nodes)})


def cheque_bounced(env):
    _ = env._
    start = n('start', 'start', 0, 0, _("Cheque bounced"), trigger='change', fields=['state'],
              domain=repr([('state', '=', 'bounced')]), becomes=True, policy='single')
    call = activity(env, 'call', 1, 0, _("Call the partner"), CREATOR,
                    _("Call {{ object.partner_id.name }} about the bounced cheque {{ object.display_name }}"),
                    kind='call')
    wait = n('wait', 'wait', 2, 0, _("3 days later"), mode='duration', amount=3, unit='days')
    check = n('open', 'condition', 3, 0, _("Still bounced?"), domain=repr([('state', '=', 'bounced')]))
    escalate = activity(env, 'escalate', 4, -1, _("Tell the manager"), _manager(env),
                        _("The bounced cheque {{ object.display_name }} is still not settled"))
    end = n('end', 'end', 5, 0, '')
    edges = chain([start, call, wait, check]) + [e('open', 'yes', 'escalate'), e('open', 'no', 'end'),
                                                 e('escalate', 'out', 'end')]
    return (_("Post-dated Cheques: Bounced"),
            _("A cheque bounces: a call to the partner, then, 3 days later and still not settled, an activity for "
              "the accounting manager."),
            {'nodes': [start, call, wait, check, escalate, end], 'edges': edges})


# key, model, builder: a template is offered once its model is installed
TEMPLATES = [
    ('bill_due_soon', 'account.move', bill_due_soon),
    ('bill_left_in_draft', 'account.move', bill_left_in_draft),
    ('bill_without_reference', 'account.move', bill_without_reference),
    ('invoice_not_sent', 'account.move', invoice_not_sent),
    ('invoice_large', 'account.move', invoice_large),
    ('payment_left_in_draft', 'account.payment', payment_left_in_draft),
    ('cheque_maturing', 'account.pdc', cheque_maturing),
    ('cheque_bounced', 'account.pdc', cheque_bounced),
]
