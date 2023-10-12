function AdvancedSurveyEdit(runtime, element) {
    var self = this;
    var notify;

    // The workbench doesn't support notifications.
    notify = typeof(runtime.notify) != 'undefined';

    this.init = function () {
        $(element).find('.cancel-button', element).bind('click', function() {
            runtime.notify('cancel', {});
        });
        $(element).find('.save-button', element).bind('click', self.surveySubmitHandler);
    };

    this.surveySubmitHandler = function () {
        // Take all of the fields, serialize them, and pass them to the
        // server for saving.
        var handlerUrl = runtime.handlerUrl(element, 'studio_submit');
        var data = {};

        data['questions'] = $('#advancedsurvey-questions-editor', element).val();
        data['feedback'] = $('#advancedsurvey-feedback-editor', element).val();
        data['max_submissions'] = $('#advancedsurvey-max-submissions', element).val();
        data['block_name'] = $('#advancedsurvey-block-name', element).val();

        if (notify) {
            runtime.notify('save', {state: 'start', message: gettext("Saving")});
        }

        $.ajax({
            type: "POST",
            url: handlerUrl,
            data: JSON.stringify(data),
            // There are issues with using proper status codes at the moment.
            // So we pass along a 'success' key for now.
            success: function(result) {
                if (result['success'] && notify) {
                    runtime.notify('save', {state: 'end'})
                } else if (notify) {
                    runtime.notify('error', {
                        'title': 'Error saving poll',
                        'message': self.format_errors(result['errors'])
                    });
                }
            }
        });
    };

    this.format_errors = function(errors) {
        var new_list = [];
        for (var line in errors) {
            // Javascript has no sane HTML escape method.
            // Do this instead.
            new_list.push($('<div/>').text(errors[line]).html())
        }
        return new_list.join('<br />')
    };

    $(function ($) {
        /* Here's where you'd do things on page load. */
        self.init();
    });
}