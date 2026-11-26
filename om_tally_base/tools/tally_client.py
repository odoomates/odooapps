""" A client of the HTTP server of Tally (TallyPrime or Tally.ERP 9, Help > Settings > Connectivity: "Client/Server
configuration", port 9000 by default). Odoo posts XML Export requests; Tally answers with XML.

The requests use the "Export Data" envelope (reports "List of Accounts" and "Day Book"), which every version of
Tally answers, and a TDL collection for the list of companies and the changes by ALTERID.
"""
import logging
from xml.sax.saxutils import escape

import requests

from .tally_xml import TallyXmlError, read_tally_objects

_logger = logging.getLogger(__name__)


class TallyConnectionError(Exception):
    pass


def _static_variables(company=None, date_from=None, date_to=None, extra=None):
    variables = {'SVEXPORTFORMAT': '$$SysName:XML'}
    if company:
        variables['SVCURRENTCOMPANY'] = company
    if date_from:
        variables['SVFROMDATE'] = date_from.strftime('%Y%m%d')
    if date_to:
        variables['SVTODATE'] = date_to.strftime('%Y%m%d')
    variables.update(extra or {})
    return ''.join(f'<{key}>{escape(str(value))}</{key}>' for key, value in variables.items())


def export_data_request(report, company=None, date_from=None, date_to=None, extra=None):
    """ An "Export Data" request of a report of Tally. """
    return (
        '<ENVELOPE><HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER><BODY><EXPORTDATA><REQUESTDESC>'
        f'<REPORTNAME>{escape(report)}</REPORTNAME>'
        f'<STATICVARIABLES>{_static_variables(company, date_from, date_to, extra)}</STATICVARIABLES>'
        '</REQUESTDESC></EXPORTDATA></BODY></ENVELOPE>'
    )


def collection_request(name, object_type, fetch, company=None, filters=None, extra=None):
    """ An Export request of a TDL collection, with formulae as filters: {name: formula}. """
    filter_tag = f'<FILTER>{",".join(filters)}</FILTER>' if filters else ''
    formulae = ''.join(
        f'<SYSTEM TYPE="Formulae" NAME="{escape(key)}">{escape(formula)}</SYSTEM>'
        for key, formula in (filters or {}).items()
    )
    return (
        '<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE>'
        f'<ID>{escape(name)}</ID></HEADER><BODY><DESC>'
        f'<STATICVARIABLES>{_static_variables(company, extra=extra)}</STATICVARIABLES>'
        f'<TDL><TDLMESSAGE><COLLECTION NAME="{escape(name)}" ISMODIFY="No"><TYPE>{escape(object_type)}</TYPE>'
        f'<FETCH>{escape(fetch)}</FETCH>{filter_tag}</COLLECTION>{formulae}</TDLMESSAGE></TDL>'
        '</DESC></BODY></ENVELOPE>'
    )


class TallyClient:
    """ Posts requests to Tally and reads the answers. """

    def __init__(self, host, port=9000, timeout=120):
        host = (host or 'localhost').strip().rstrip('/')
        if not host.startswith(('http://', 'https://')):
            host = 'http://' + host
        self.url = f'{host}:{port}' if port and host.count(':') < 2 else host
        self.timeout = timeout

    def post(self, body):
        """ The raw answer of Tally to an XML request. """
        try:
            response = requests.post(self.url, data=body.encode('utf-8'), timeout=self.timeout,
                                     headers={'Content-Type': 'text/xml; charset=utf-8'})
        except requests.exceptions.ConnectionError as error:
            raise TallyConnectionError(
                f"Tally does not answer at {self.url}. Check that Tally is open with a company loaded, that it acts "
                f"as a server on this port, and that a firewall does not block it.") from error
        except requests.exceptions.Timeout as error:
            raise TallyConnectionError(f"Tally did not answer within {self.timeout} seconds.") from error
        if response.status_code != 200:
            raise TallyConnectionError(f"Tally answered with HTTP {response.status_code}.")
        return response.content

    def request(self, body):
        """ (records, raw answer): see read_tally_objects. """
        data = self.post(body)
        try:
            objects = read_tally_objects(data)
        except TallyXmlError as error:
            raise TallyConnectionError(f"The answer of Tally cannot be read: {error}") from error
        if objects['errors']:
            raise TallyConnectionError("Tally: " + "; ".join(objects['errors'][:5]))
        return objects, data

    def companies(self):
        """ The companies open in Tally. """
        body = collection_request('OMCompanyList', 'Company',
                                  'NAME,GUID,BOOKSFROM,STARTINGFROM,BASICCURRENCYSYMBOL,STATENAME,COUNTRYNAME')
        return self.request(body)[0]['COMPANY']

    def masters(self, company):
        """ All the masters of a company: groups, ledgers, voucher types, cost centres, stock... """
        return self.request(export_data_request('List of Accounts', company,
                                                extra={'ACCOUNTTYPE': 'All Masters'}))

    def company_details(self, company):
        body = collection_request('OMCompanyDetails', 'Company', '*', company=company)
        return [values for values in self.request(body)[0]['COMPANY'] if values['name'] == company]

    def vouchers(self, company, date_from, date_to):
        """ The vouchers of a period (the Day Book, with all their details). """
        return self.request(export_data_request('Day Book', company, date_from, date_to,
                                                extra={'EXPLODEFLAG': 'Yes'}))

    def vouchers_altered_after(self, company, alter_id):
        """ The vouchers created or changed after an ALTERID. """
        body = collection_request(
            'OMVouchersAltered', 'Voucher',
            '*,ALLLEDGERENTRIES.LIST.*,ALLINVENTORYENTRIES.LIST.*,LEDGERENTRIES.LIST.*,INVENTORYENTRIES.LIST.*',
            company=company, filters={'OMAlteredAfter': f'$AlterID > {int(alter_id)}'})
        return self.request(body)
