import pkg_resources
from web_fragments.fragment import Fragment
from xblock.core import XBlock
from xblock.fields import Scope, List, Dict, Integer, String
from xblockutils.resources import ResourceLoader
from xblockutils.settings import XBlockWithSettingsMixin
from xblockutils.publish_event import PublishEventMixin
from xblock.completable import XBlockCompletionMode
from .utils import DummyTranslationService, _
from django import utils
import six
import time
import json

try:
    # pylint: disable=import-error, bad-option-value, ungrouped-imports
    from django.conf import settings
    from api_manager.models import GroupProfile
    HAS_GROUP_PROFILE = True
except ImportError:
    HAS_GROUP_PROFILE = False

class ResourceMixin(XBlockWithSettingsMixin):
    loader = ResourceLoader(__name__)

    @staticmethod
    def resource_string(path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    @property
    def i18n_service(self):
        """ Obtains translation service """
        return self.runtime.service(self, "i18n") or DummyTranslationService()

    def get_translation_content(self):
        try:
            return self.resource_string('public/js/translations/{lang}/textjs.js'.format(
                lang=utils.translation.to_locale(utils.translation.get_language()),
            ))
        except IOError:
            return self.resource_string('public/js/translations/en/textjs.js')

    def create_fragment(self, context, template, css, js, js_init):
        frag = Fragment()
        frag.add_content(self.loader.render_django_template(
            template,
            context=context,
            i18n_service=self.i18n_service
        ))

        frag.add_css(self.resource_string(css))

        frag.add_javascript(self.resource_string(js))
        frag.add_javascript(self.get_translation_content())
        frag.initialize_js(js_init)
        return frag
    
    def _get_block_id(self):
        """
        Returns unique ID of this block. Useful for HTML ID attributes.

        Works both in LMS/Studio and workbench runtimes:
        - In LMS/Studio, use the location.html_id method.
        - In the workbench, use the usage_id.
        """
        if hasattr(self, 'location'):
            return self.location.html_id()  # pylint: disable=no-member

        return six.text_type(self.scope_ids.usage_id)

class CSVExportMixin(object):
    """
    Allows Surveys XBlocks to support CSV downloads of all users'
    details per block.
    """
    active_export_task_id = String(
        # The UUID of the celery AsyncResult for the most recent export,
        # IF we are sill waiting for it to finish
        default="",
        scope=Scope.user_state_summary,
    )
    last_export_result = Dict(
        # The info dict returned by the most recent successful export.
        # If the export failed, it will have an "error" key set.
        default=None,
        scope=Scope.user_state_summary,
    )

    @XBlock.json_handler
    def csv_export(self, data, suffix=''):
        """
        Asynchronously export given data as a CSV file.
        """
        # Launch task
        from .tasks import export_csv_data  # Import here since this is edX LMS specific

        # Make sure we nail down our state before sending off an asynchronous task.
        async_result = export_csv_data.delay(
            six.text_type(getattr(self.scope_ids, 'usage_id', None)),
            six.text_type(getattr(self.runtime, 'course_id', 'course_id')),
        )
        if not async_result.ready():
            self.active_export_task_id = async_result.id
        else:
            self._store_export_result(async_result)

        return self._get_export_status()

    @XBlock.json_handler
    def get_export_status(self, data, suffix=''):
        """
        Return current export's pending status, previous result,
        and the download URL.
        """
        return self._get_export_status()

    def _get_export_status(self):
        self.check_pending_export()
        return {
            'export_pending': bool(self.active_export_task_id),
            'last_export_result': self.last_export_result,
            'download_url': self.download_url_for_last_report,
        }

    def check_pending_export(self):
        """
        If we're waiting for an export, see if it has finished, and if so, get the result.
        """
        from .tasks import export_csv_data  # Import here since this is edX LMS specific
        if self.active_export_task_id:
            async_result = export_csv_data.AsyncResult(self.active_export_task_id)
            if async_result.ready():
                self._store_export_result(async_result)

    @property
    def download_url_for_last_report(self):
        """ Get the URL for the last report, if any """
        from lms.djangoapps.instructor_task.models import ReportStore  # pylint: disable=import-error

        # Unfortunately this is a bit inefficient due to the ReportStore API
        if not self.last_export_result or self.last_export_result['error'] is not None:
            return None

        report_store = ReportStore.from_config(config_name='GRADES_DOWNLOAD')
        course_key = getattr(self.scope_ids.usage_id, 'course_key', None)
        return dict(report_store.links_for(course_key)).get(self.last_export_result['report_filename'])

    def student_module_queryset(self):
        try:
            from lms.djangoapps.courseware.models import StudentModule  # pylint: disable=import-error
        except RuntimeError:
            from courseware.models import StudentModule
        return StudentModule.objects.select_related('student').filter(
            course_id=self.runtime.course_id,
            module_state_key=self.scope_ids.usage_id,
        ).order_by('-modified')

    def _store_export_result(self, task_result):
        """ Given an AsyncResult or EagerResult, save it. """
        self.active_export_task_id = ''
        if task_result.successful():
            if isinstance(task_result.result, dict) and not task_result.result.get('error'):
                self.last_export_result = task_result.result
            else:
                self.last_export_result = {'error': u'Unexpected result: {}'.format(repr(task_result.result))}
        else:
            self.last_export_result = {'error': six.text_type(task_result.result)}

    def prepare_data(self):
        """
        Return a two-dimensional list containing cells of data ready for CSV export.
        """
        raise NotImplementedError

    def get_filename(self):
        """
        Return a string to be used as the filename for the CSV export.
        """
        raise NotImplementedError


@XBlock.wants('settings')
@XBlock.needs('i18n')
class AdvancedSurveyXBlock(XBlock, ResourceMixin, PublishEventMixin, CSVExportMixin):
    """
    Adds advanced surveys that can include sections with headers and multiple questions
    """
    completion_mode = XBlockCompletionMode.COMPLETABLE
    has_custom_completion = True
    has_author_view = True
    event_namespace = 'xblock.advancedsurvey'
    
    display_name = String(default=_('Advanced Survey'))
    block_name = String(default=_('Advanced Survey'))

    max_submissions = Integer(default=1, help=_("The maximum number of times a user may submit the survey."))
    submissions_count = Integer(
        default=0, help=_("Number of times the user has submitted the survey."), scope=Scope.user_state
    )
    feedback = String(default="Thank you for submitting this survey!", help=_("Text to display after the user submits the survey."))

    questions = List(
        default=[
            {'question_id': 0, 'type': "rate", 'header': "Content", 'prompts':[[0, "Content was useful"], [1, "Content was well structured"], [2, "Content was rich"]], 'options': [[0, "Excellent"], [1, "Very Good"], [2, "Good"], [3, "Okay"], [4, "Not Okay"]]},
            {'question_id': 1, 'type': "rate", 'prompts':[[0, "How do you describe the number of lessons"], [1, "How do you describe the size of each lesson"]], 'options': [[0, "Low/Small"], [1, "Fair"], [2, "High/Big"]]},
            {'question_id': 2, 'type': "rate", 'header': "Instructor", 'prompts':[[0, "Spoke clearly"], [1, "Explained complex issues"], [2, "Gives examples"]], 'options': [[0, "Excellent"], [1, "Very Good"], [2, "Good"], [3, "Okay"], [4, "Not Okay"]]},
            {'question_id': 3, 'type': "free", 'required': True, 'header': "Tell us more", 'prompt': "What are some things you liked about this course?"},
            {'question_id': 4, 'type': "free", 'prompt': "What are some things you did not like about this course?"}
        ],
        scope=Scope.settings, help=_("Questions for this Survey")
    )

    answers = Dict(help=_("The user's answers"), scope=Scope.user_state, default={'q-3': 'hello!!!!', 'q-0-p-1': 'o-1', 'q-0-p-2': 'o-4'})

    def send_submit_event(self, answers):
        # Let the LMS know the user has submitted the survey.
        self.runtime.publish(self, 'completion', {'completion': 1.0})
        # The SDK doesn't set url_name.
        event_dict = {'url_name': getattr(self, 'url_name', '')}
        event_dict.update(answers)
        self.publish_event_from_dict(
            self.event_namespace + '.submitted',
            event_dict,
        )

    def questions_to_json(self):
        return json.dumps(self.questions)

    def json_string_to_questions(self, json_string):
        return json.loads(json_string)
    
    def can_submit(self):
        """
        Checks to see if the user is permitted to submit. This may not be the case if they used up their max_submissions.
        """
        return self.max_submissions == 0 or self.submissions_count < self.max_submissions

    def can_view_results(self):
        """
        Checks to see if the user has permissions to view results.
        This only works inside the LMS.
        """
        if not hasattr(self.runtime, 'user_is_staff'):
            return False

        # Course staff users have permission to view results.
        if self.runtime.user_is_staff:
            return True

        # Check if user is member of a group that is explicitly granted
        # permission to view the results through django configuration.
        if not HAS_GROUP_PROFILE:
            return False

        group_names = getattr(settings, 'XBLOCK_ADVANCEDSURVEY_EXTRA_VIEW_GROUPS', [])
        if not group_names:
            return False
        user = self.runtime.get_real_user(self.runtime.anonymous_student_id)
        group_ids = user.groups.values_list('id', flat=True)
        return GroupProfile.objects.filter(group_id__in=group_ids, name__in=group_names).exists()

    def author_view(self, context=None):
        """
        Used to hide CSV export in Studio view
        """
        if not context:
            context = {}

        context['studio_edit'] = True
        return self.student_view(context)

    def student_view(self, context=None):
        """
        The primary view of the AdvancedSurveyXBlock, shown to students
        when viewing courses.
        """
        if not context:
            context = {}

        context.update({
            'questions': self.questions,
            'answers': self.answers,
            'block_id': self._get_block_id(),
            'usage_id': six.text_type(self.scope_ids.usage_id),
            'can_submit': self.can_submit(),
            'can_view_results': self.can_view_results(),
            'block_name': self.block_name,
            'feedback': self.feedback
        })

        return self.create_fragment(
            context,
            template="static/html/advancedsurvey.html",
            css="static/css/advancedsurvey.css",
            js="static/js/src/advancedsurvey.js",
            js_init="AdvancedSurveyXBlock"
        )

    def studio_view(self, context=None):
        if not context:
            context = {}

        context.update({
            'feedback': self.feedback,
            'questions': self.questions_to_json(),
            'max_submissions': self.max_submissions,
            'block_name': self.block_name
        })
        return self.create_fragment(
            context,
            template="static/html/advancedsurvey_edit.html",
            css="static/css/advancedsurvey_edit.css",
            js="static/js/src/advancedsurvey_edit.js",
            js_init="AdvancedSurveyEdit"
        )

    def get_answers(self):
        """
        Gets the user's answers, if they're still valid.
        TODO: This method currently only checks if all required questions are answered
        but its true purpose is to check whether questions changed and there are answers
        for no questions, or questions without answers
        Therefore right now only 1 max submission is allowed
        """
        questions = list(self.questions)

        if self.answers is None:
            return None
        
        for question in questions:
            question_id = question['question_id']
            if question['type'] == 'rate':
                for prompt in question['prompts']:
                    answer = self.answers.get(f"q-{question_id}-p-{prompt[0]}", None)
                    if answer is None or answer == 'none':
                        return None
            elif question['type'] == 'free':
                answer = self.answers.get(f"q-{question_id}", None)
                if question.get('required', False) and (answer is None or answer == ''):
                    return None
        
        return self.answers

    @XBlock.json_handler
    def submit(self, data, suffix=''):
        """
        Submit the user's answers
        """
        questions = list(self.questions)
        result = {'success': True, 'errors': []}
        answers = self.get_answers()
        if answers:
            result['success'] = False
            result['errors'].append(self.ugettext("You have already answered this survey."))
            return result

        if not answers:
            # Reset submissions count if answers are bogus
            self.submissions_count = 0

        if not self.can_submit():
            result['success'] = False
            result['errors'].append(self.ugettext('You have already answered this survey as many times as you are allowed to.'))
            return result

        # Make sure the user has included all questions
        all_answered = True
        cleaned_answers = {}
        for question in questions:
            question_id = question['question_id']
            if question['type'] == 'rate':
                for prompt in question['prompts']:
                    answer = data.get(str(question_id), {}).get(str(prompt[0]), None)
                    if answer is None or answer == 'none':
                        all_answered = False
                        result['success'] = False
                        result['errors'].append(self.ugettext('You did not answer all required questions.'))
                        return result
                    cleaned_answers[f"q-{question_id}-p-{prompt[0]}"] = answer
            elif question['type'] == 'free':
                answer = data.get(str(question_id), None)
                if question.get('required', False) and (answer is None or answer == ''):
                    all_answered = False
                    result['success'] = False
                    result['errors'].append(self.ugettext('You did not answer all required questions.'))
                    return result
                cleaned_answers[f"q-{question_id}"] = answer
    
        if not result['success']:
            result['can_submit'] = self.can_submit()
            return result

        # Record the submission!
        self.answers = cleaned_answers

        self.submissions_count += 1
        self.send_submit_event({'answers': self.answers})
        result['can_submit'] = self.can_submit()
        result['submissions_count'] = self.submissions_count
        result['max_submissions'] = self.max_submissions

        return result

    @XBlock.json_handler
    def studio_submit(self, data, suffix=''):
        result = {'success': True, 'errors': []}
        questions = data.get('questions', '').strip()
        feedback = data.get('feedback', '').strip()
        max_submissions = int(data['max_submissions'])
        block_name = data.get('block_name', '').strip()

        if not questions:
            result['errors'].append(self.ugettext("You must add questions."))
            result['success'] = False

        if not result['success']:
            return result

        self.questions = self.json_string_to_questions(questions)
        self.feedback = feedback
        self.max_submissions = max_submissions
        self.block_name = block_name

        return result

    def prepare_data(self):
        """
        Return a two-dimensional list containing cells of data ready for CSV export.
        """
        header_row = ['user_id', 'username', 'user_email']
        question_prefix = ""
        for question in self.questions:
            if 'header' in question:
                question_prefix = f"{question['header']}: "

            if question['type'] == 'rate':
                for prompt in question['prompts']:
                    header_row.append(f"{question_prefix}{prompt[1]}")
            elif question['type'] == 'free':
                header_row.append(f"{question_prefix}{question['prompt']}")

        data = {}
        for sm in self.student_module_queryset():
            state = json.loads(sm.state)
            if sm.student.id not in data and state.get('answers'):
                row = [
                    sm.student.id,
                    sm.student.username,
                    sm.student.email,
                ]
                for question in self.questions:
                    answers = state.get('answers')
                    question_key = f"q-{question['question_id']}"
                    if question['type'] == 'rate':
                        options_map = {}
                        for option in question['options']:
                            options_map[str(option[0])] = option[1]

                        for prompt in question['prompts']:
                            answer_id = f"{question_key}-p-{prompt[0]}"
                            if answer_id in answers:
                                option_id = answers[answer_id].split('-')[1]
                                row.append(options_map[option_id])
                    elif question['type'] == 'free':
                        if question_key in answers:
                            row.append(answers[question_key])
                data[sm.student.id] = row
        return header_row + list(data.values())

    def get_filename(self):
        """
        Return a string to be used as the filename for the CSV export.
        """
        return u"advancedsurvey-data-export-{}.csv".format(time.strftime("%Y-%m-%d-%H%M%S", time.gmtime(time.time())))

    # TO-DO: change thi{s to create the scenarios you'd like to see in the
    # workbench while developing your XBlock.
    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("AdvancedSurveyXBlock",
             """<advancedsurvey/>
             """),
            ("Multiple AdvancedSurveyXBlock",
             """<vertical_demo>
                <advancedsurvey/>
                <advancedsurvey/>
                <advancedsurvey/>
                </vertical_demo>
             """),
        ]
