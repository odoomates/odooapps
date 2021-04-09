odoo.define('pdf_report_options.report', function(require) {
    'use strict';

    var ActionManager = require('web.ActionManager');
    var core = require('web.core');
    var framework = require('web.framework');
    var session = require('web.session');
    var Dialog = require('web.Dialog');

    var QWeb = core.qweb;
    var _t = core._t;
    var _lt = core._lt;

    // Messages that will be shown to the user (if needed).
    var WKHTMLTOPDF_MESSAGES = {
        'install': _lt('Unable to find Wkhtmltopdf on this \nsystem. The report will be shown in html.<br><br><a href="http://wkhtmltopdf.org/" target="_blank">\nwkhtmltopdf.org</a>'),
        'workers': _lt('You need to start OpenERP with at least two \nworkers to print a pdf version of the reports.'),
        'upgrade': _lt('You should upgrade your version of\nWkhtmltopdf to at least 0.12.0 in order to get a correct display of headers and footers as well as\nsupport for table-breaking between pages.<br><br><a href="http://wkhtmltopdf.org/" \ntarget="_blank">wkhtmltopdf.org</a>'),
        'broken': _lt('Your installation of Wkhtmltopdf seems to be broken. The report will be shown in html.<br><br><a href="http://wkhtmltopdf.org/" target="_blank">wkhtmltopdf.org</a>')
    };

    ActionManager.include({
        _showDialogPdfOption: function(action, options) {
            var self = this;
            var btnClose = function() {
                $('#frame-pdf').remove();
                this.close();
            }
            var $dialog = new Dialog(self, {
                title: _t("What do you want to do?"),
                size: 'medium',
                $content: QWeb.render('print_attachment_options.button_options'),
                buttons: [{ text: _t('Close'), click: btnClose }]
            }).open();
            $dialog.opened().then(function() {
                $dialog.$('.btn-pdf').on('click', function(e) {
                    self.pdfReportOption = e.currentTarget.dataset.optionPdf;
                    //trigger the download of the PDF report
                    return self._triggerDownload(action, options, 'pdf');
                });
            });
        },
        _downloadReport: function (url) {
            var self = this;
            framework.blockUI();
            return new Promise(function (resolve, reject) {
                var type = 'qweb-' + url.split('/')[2];
                var blocked = !session.get_file({
                    url: '/report/download',
                    data: {
                        data: JSON.stringify([url, type, self.pdfReportOption]),
                        context: JSON.stringify(session.user_context),
                    },
                    success: resolve,
                    error: (error) => {
                        self.call('crash_manager', 'rpc_error', error);
                        reject();
                    },
                    complete: framework.unblockUI,
                });
                if (blocked) {
                    // AAB: this check should be done in get_file service directly,
                    // should not be the concern of the caller (and that way, get_file
                    // could return a promise)
                    var message = _t('A popup window with your report was blocked. You ' +
                                     'may need to change your browser settings to allow ' +
                                     'popup windows for this page.');
                    self.do_warn(_t('Warning'), message, true);
                }
            });
        },
        _executeReportAction: function(action, options) {
            var self = this;
            self.pdfReportOption = '';
            if (action.report_type === 'qweb-html') {
                return this._executeReportClientAction(action, options);
            } else if (action.report_type === 'qweb-pdf') {
                // check the state of wkhtmltopdf before proceeding
                return this.call('report', 'checkWkhtmltopdf').then(function(state) {
                    // display a notification according to wkhtmltopdf's state
                    if (state in WKHTMLTOPDF_MESSAGES) {
                        self.do_notify(_t('Report'), WKHTMLTOPDF_MESSAGES[state], true);
                    }
                    if (state === 'upgrade' || state === 'ok') {
                        if (action.default_print_option) {
                            self.pdfReportOption = action.default_print_option;
                            return self._triggerDownload(action, options, 'pdf');
                        } else {
                            return self._showDialogPdfOption(action, options);
                        }
                    } else {
                        // open the report in the client action if generating the PDF is not possible
                        return self._executeReportClientAction(action, options);
                    }
                });
            } else if (action.report_type === 'qweb-text') {
                return self._triggerDownload(action, options, 'text');
            } else if (action.report_type === 'xlsx') {
                return self._triggerDownload(action, options, 'xlsx');
            }
            else {
                console.error("The ActionManager can't handle reports of type " +
                    action.report_type, action);
                return Promise.reject();
            }
        }
    });
});
