/* Javascript for AdvancedSurveyXBlock. */

// Used to delay a funciton call by some timeout (default 300 ms)
function debounce(func, timeout = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => { func.apply(this, args); }, timeout);
    };
}

function AdvancedSurveyXBlock(runtime, element) {
    var self = this;
    var exportStatus = {};

    this.getAnswers = function() {
        // Group radio answers by question, then prompt
        let answers = {};
        this.radios.each((_index, el) => {
            const idSplit = el.id.split('-');
            const questionId = idSplit[1];
            const promptId = idSplit[3];
            const optionId = idSplit[5];
            
            if (!(questionId in answers))
                answers[questionId] = {};
            if (!(promptId in answers[questionId]))
                answers[questionId][promptId] = 'none';
            if (el.checked)
                answers[questionId][promptId] = "o-" + optionId;
        });
        
        // Add free questions' answers
        this.textAreas.each((_index, el) => {
            const questionId = el.id.split('-')[1];
            answers[questionId] = el.value;
        });
        
        return answers;
    };

    this.init = function() {
        // Initialization function for the Advanced Survey Block
        this.submitUrl = runtime.handlerUrl(element, 'submit');
        this.csv_url= runtime.handlerUrl(element, 'csv_export');

        this.submit = $('input[type=button]', element);
        
        this.exportResultsButton = $('.export-results-button', element);
        this.exportResultsButton.click(this.exportCsv);

        this.downloadResultsButton = $('.download-results-button', element);
        this.downloadResultsButton.click(this.downloadCsv);

        this.errorMessage = $('.error-message', element);

        this.radios = $('input[type=radio]', element);
        this.textAreas = $('textarea', element);

        // If the user is unable to vote, disable input.
        if (! $('div.advancedsurvey_block', element).data('can-submit')) {
            this.radios.attr('disabled', true);
            this.textAreas.attr('disabled', true);
            self.disableSubmit();
            return
        }
        
        self.radios.bind("change.verifySubmittable", self.verifySubmittable);
        self.textAreas.bind("input.verifySubmittable", debounce(() => self.verifySubmittable()));

        self.submit.click(function () {
            // Disable the submit button to avoid multiple clicks
            self.disableSubmit();
            $.ajax({
                type: "POST",
                url: self.submitUrl,
                data: JSON.stringify(self.getAnswers()),
                success: self.onSubmit
            })
        });

        // If the user has refreshed the page, they may still have an answer
        // selected and the submit button should be enabled.
        self.verifySubmittable()
    };

    this.verifySubmittable = function() {
        let answers = self.getAnswers();
        
        // Verify that all radio questions have an answer selected
        var doEnable = true;
        self.radios.each((_index, el) => {
            const idSplit = el.id.split('-');
            const questionId = idSplit[1];
            const promptId = idSplit[3];
            if (answers[questionId][promptId] === 'none') {
                doEnable = false;
                return;
            }
        });

        // Verify that all required free questions have an answer
        self.textAreas.each((_index, el) => {
            if (el.required && el.value === '') {
                doEnable = false;
                return;
            }
        });

        // Enable or disable the submit button
        if (doEnable)
            self.enableSubmit();
        else
            self.disableSubmit();
    }

    this.onSubmit = function (data) {
        // Fetch the results from the server and render them.
        if (!data['success']) {
            alert(data['errors'].join('\n'));
        }
        var can_submit = data['can_submit'];
        if (!can_submit) {
            // Disable all types of input within the survey
            $('input', element).attr('disabled', true);
            $('textarea', element).attr('disabled', true);
            self.disableSubmit();
        } else {
            // Enable the submit button.
            self.enableSubmit();
        }
        return;
    };

    this.disableSubmit = function() {
        // Disable the submit button.
        self.submit.attr("disabled", true);
    }

    this.enableSubmit = function () {
        // Enable the submit button.
        self.submit.removeAttr("disabled");
    };

    function getStatus() {
        $.ajax({
            type: 'POST',
            url: runtime.handlerUrl(element, 'get_export_status'),
            data: '{}',
            success: updateStatus,
            dataType: 'json'
        });
    }

    function updateStatus(newStatus) {
        var statusChanged = ! _.isEqual(newStatus, exportStatus);
        exportStatus = newStatus;
        if (exportStatus.export_pending) {
            // Keep polling for status updates when an export is running.
            setTimeout(getStatus, 1000);
        }
        else {
            if (statusChanged) {
                if (newStatus.last_export_result.error) {
                    self.errorMessage.text("Error: " + newStatus.last_export_result.error);
                    self.errorMessage.show();
                } else {
                    self.downloadResultsButton.attr('disabled', false);
                    self.errorMessage.hide()
                }
            }
        }
    }

    this.exportCsv = function() {
        $.ajax({
            type: "POST",
            url: self.csv_url,
            data: JSON.stringify({}),
            success: updateStatus
        });
    };

    this.downloadCsv = function() {
        window.location = exportStatus.download_url;
    };

    $(function ($) {
        /* Here's where you'd do things on page load. */
        self.init();
    });
}
