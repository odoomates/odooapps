from itertools import pairwise

from odoo.tests import TransactionCase, new_test_user


def node(node_id, kind, **config):
    return {'id': node_id, 'type': kind, 'x': 0, 'y': 0, 'label': config.pop('label', ''), 'config': config}


def chain(*nodes, branches=()):
    """ A graph of ``nodes`` linked one after the other by their first exit,
    plus the ``(source, port, target)`` arrows of ``branches``. """
    from odoo.addons.om_automation_studio.tools import NODE_PORTS  # noqa: PLC0415
    edges = []
    taken = {(source, port) for source, port, __ in branches}
    for previous, following in pairwise(nodes):
        ports = NODE_PORTS[previous['type']]
        if ports and (previous['id'], ports[0]) not in taken:
            edges.append({'id': f"e{len(edges)}", 'source': previous['id'], 'port': ports[0],
                          'target': following['id']})
    for source, port, target in branches:
        edges.append({'id': f"e{len(edges)}", 'source': source, 'port': port, 'target': target})
    return {'nodes': list(nodes), 'edges': edges}


class WorkflowCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nolog=True))
        cls.Workflow = cls.env['om.workflow']
        cls.Run = cls.env['om.workflow.run']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.approver = new_test_user(cls.env, 'om_wd_approver', groups='base.group_user')
        cls.other_user = new_test_user(cls.env, 'om_wd_other', groups='base.group_user')
        cls.supervisor = new_test_user(
            cls.env, 'om_wd_supervisor',
            groups='base.group_user,om_automation_studio.om_automation_studio_group_supervisor')

    def make_workflow(self, graph, publish=True, **vals):
        workflow = self.Workflow.create({
            'name': 'Test Workflow',
            'model_id': self.partner_model.id,
            'graph': graph,
            **vals,
        })
        if publish:
            workflow.action_publish()
        return workflow

    def runs_of(self, workflow, partner=None):
        domain = [('workflow_id', '=', workflow.id)]
        if partner:
            domain.append(('res_id', '=', partner.id))
        return self.Run.search(domain)

    def path(self, run):
        return [(step.node_key, step.port or '') for step in run.step_ids.sorted('id')]
