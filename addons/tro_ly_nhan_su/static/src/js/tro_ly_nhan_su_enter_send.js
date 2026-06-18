odoo.define('tro_ly_nhan_su.enter_send', function (require) {
    'use strict';

    /**
     * Submit trợ lý AI bằng phím Enter.
     *
     * - Enter: gửi câu hỏi.
     * - Shift + Enter: xuống dòng.
     * - Ctrl/Alt/Meta + Enter: giữ nguyên hành vi mặc định.
     *
     * Dùng event delegation để hoạt động cả trong modal wizard được render động.
     */
    function findAssistantContainer(node) {
        if (!node || !node.closest) {
            return null;
        }

        var form = node.closest('.o_tro_ly_ai_form');
        if (form) {
            return form;
        }

        var sheetContainer = node.closest('.modal, .o_dialog, .o_form_view');
        if (!sheetContainer) {
            return null;
        }

        if (sheetContainer.querySelector('.o_tro_ly_ai_sheet')) {
            return sheetContainer;
        }

        var titleNode = sheetContainer.querySelector('.modal-title, .o_dialog_title, header, h1');
        var titleText = titleNode && titleNode.textContent || '';
        if (titleText.indexOf('Trợ lý AI nhân sự') !== -1) {
            return sheetContainer;
        }

        if (sheetContainer.textContent && sheetContainer.textContent.indexOf('Trợ lý AI nhân sự') !== -1) {
            return sheetContainer;
        }

        return null;
    }

    function findSendButton(container) {
        if (!container) {
            return null;
        }
        var button = container.querySelector(
            '.o_tro_ly_ai_send, ' +
            'button[name="action_hoi"], ' +
            'button[data-name="action_hoi"], ' +
            '.modal-footer button.btn-primary'
        );
        if (button) {
            return button;
        }

        var buttons = container.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
            if ((buttons[i].textContent || '').trim() === 'Gửi câu hỏi') {
                return buttons[i];
            }
        }
        return null;
    }

    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Enter' || ev.shiftKey || ev.ctrlKey || ev.altKey || ev.metaKey) {
            return;
        }

        var textarea = ev.target;
        if (!textarea || textarea.tagName !== 'TEXTAREA') {
            return;
        }

        var container = findAssistantContainer(textarea);
        if (!container) {
            return;
        }

        var question = (textarea.value || '').trim();
        if (!question) {
            return;
        }

        var sendButton = findSendButton(container);
        if (!sendButton || sendButton.disabled) {
            return;
        }

        ev.preventDefault();
        ev.stopPropagation();

        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.blur();

        window.setTimeout(function () {
            sendButton.click();
        }, 0);
    }, true);
});
