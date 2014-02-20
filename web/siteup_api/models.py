import logging
logger = logging.getLogger(__name__)

from itertools import chain
import re
from datetime import datetime

from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext, ugettext_lazy as _
from django.core import validators

from siteup_checker import monitoring
from .validators import ValidateAnyOf, validate_ip_or_hostname, validate_hostname

####################################################################################
# Log related models

class CheckLog(models.Model):
    """Stores the result of the check."""

    date = models.DateTimeField(
        auto_now_add=True
    )

    STATUSES = (
        (0, 'Up'),
        (1, 'Down'),
        (2, 'Error'),
    )

    status = models.IntegerField(
        default=0,
        choices=STATUSES
    )

    status_extra = models.CharField(
        max_length=255
    )

    response_time = models.IntegerField(
        default=0
    )


    def save(self):
        super(CheckLog, self).save()
        self.check.update_status(self)


    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    check = generic.GenericForeignKey('content_type', 'object_id')


class CheckStatus(models.Model):
    status = models.IntegerField(
        default=0
    )

    date_start = models.DateTimeField()

    date_end = models.DateTimeField(
        null=True
    )

    notified = models.BooleanField(
        default=False
    )

    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    check = generic.GenericForeignKey('content_type', 'object_id')

    def get_date_start(self):
        return self.date_start.isoformat()

    def get_date_end(self):
        if self.date_end:
            return self.date_end.isoformat()
        else:
            return datetime.now().isoformat()


####################################################################################


class BaseCheck(models.Model):
    """Base model for the checks. It groups the common fields and relations.
    It's an abstract base class, so no actual table is created for this model."""

    title = models.CharField(
        max_length=70,
        help_text=_("Short title for the check"))

    description = models.TextField(
        blank=True,
        help_text=_("Larger description, you can include notes."))

    is_active = models.BooleanField(
        default=True,
        help_text=_("Enables or disables the check"))

    check_interval = models.PositiveSmallIntegerField(
        default=1,
        help_text=_("In minutes. How often the check should be triggered."))

    notify_email = models.BooleanField(
        default=True,
        help_text=_("Notify changes of the status of this check via email."))

    last_log_datetime = models.DateTimeField(
        blank=True,
        null=True
    )

    group = models.ForeignKey('CheckGroup')

    logs = generic.GenericRelation('CheckLog')

    statuses = generic.GenericRelation('CheckStatus')
    last_status = models.ForeignKey('CheckStatus', null=True)

    def update_status(self, check_log):
        self.last_log_datetime = check_log.date

        if not self.last_status or self.last_status.status != check_log.status:

            if self.last_status and self.last_status.status != check_log.status:
                self.last_status.date_end = check_log.date
                self.last_status.save()

            s = CheckStatus()
            s.status = check_log.status
            s.date_start = check_log.date
            s.check = self
            s.save()

            self.last_status = s
            self.save()

    def should_run_check(self):
        """Confirms that the check can be run, because it's both active and enough time has passed since the last
        time it ran. """

        if not self.is_active:
            return False

        # If check's just been created, force check
        if self.last_log_datetime is None:
            return True

        # Subtract some seconds from the difference to handle timing deviations
        elapsed_seconds = (datetime.now() - self.last_log_datetime).seconds
        if elapsed_seconds < self.check_interval * 60 - 6:
            logger.info("Check %s will not run (elapsed time: %i seconds)" % (self.title, elapsed_seconds))
            return False

        logger.info("Check %s will run (elapsed time: %i seconds)" % (self.title, elapsed_seconds))
        return True

    def edit_url(self):
        return self.__class__.__name__.lower() + "_edit"

    def delete_url(self):
        return self.__class__.__name__.lower() + "_delete"

    def activate_url(self):
        return self.__class__.__name__.lower() + "_activate"

    def deactivate_url(self):
        return self.__class__.__name__.lower() + "_deactivate"

    def unique_name(self):
        return self.__class__.__name__.lower() + str(self.pk)

    def type_name(self):
        return self.__class__.__name__.lower()

    class Meta:
        abstract = True


#######################################################################################################################
# Concrete Check Models

class PingCheck(BaseCheck):

    target = models.CharField(
        max_length=255, blank=False,
        help_text=_("Should be a hostname or an IP"),
        validators=[validate_ip_or_hostname])

    should_check_timeout = models.BooleanField(
        default=False,
        help_text=_("If active, triggers an alarm if the ping is larger than a certain value."))

    timeout_value = models.PositiveSmallIntegerField(
        null=True, blank=True,
        default=200,
        validators=[ValidateAnyOf([validators.MaxValueValidator(1000), validators.MinValueValidator(50)])],
        help_text=_("Maximum timeout for the ping. Only works if previous option is active."))

    def run_check(self):
        if not self.should_run_check():
            return

        # Initialize the log instance
        log = CheckLog(check=self)
        log.status = 0

        # Fire the ping
        check_result = monitoring.check_ping(self.target)

        # Ping properly finished
        if check_result['valid']:

            # Save ping average response time
            log.response_time = check_result['avg']

            # If most pings were received
            if check_result['received'] / check_result['transmitted'] >= 0.5:

                # Check if response time is within boundaries
                if self.should_check_timeout and int(check_result['avg']) > self.timeout_value:
                    log.status = 1
                    log.status_extra = 'Ping max response time exceeded' # TODO: i18n these strings

            # Most pings were lost
            else:
                log.status = 1
                log.status_extra = 'Most packets were lost'

        # Ping could not be launched
        else:
            log.status = 2
            log.status_extra = 'Incorrect host'

        logger.info('Save CheckLog, status %i, status_extra "%s"' % (log.status, log.status_extra))
        log.save()

    class Meta:
        verbose_name = _("ping check")
        verbose_name_plural = _("ping checks")

class PortCheck(BaseCheck):

    target = models.CharField(
        max_length=255, blank=False,
        help_text=_("Should be a hostname or an IP"),
        validators=[validate_ip_or_hostname])

    target_port = models.PositiveSmallIntegerField(
        help_text=_("Remote network port to check"),
        validators=[validators.MinValueValidator(1),
                    validators.MaxValueValidator(65535)])

    should_check_response = models.BooleanField(default=False,
        help_text=_("If active, the response from the port should contain the text in the following field."))

    response_value = models.CharField(max_length=255, blank=True,
        help_text=_("If the previous option is active, the response should contain this text."))

    def run_check(self):
        if not self.should_run_check():
            return

            # TODO

    class Meta:
        verbose_name = _("port check")
        verbose_name_plural = _("port checks")


class HttpCheck(BaseCheck):

    target = models.CharField(
        max_length=255, blank=False,
        help_text=_("Should be a valid http(s) URL"),
        validators=[validators.URLValidator()])

    status_code = models.PositiveSmallIntegerField(
        default=200,
        help_text=_("HTTP response status code that should be received from the server"),
        validators=[validators.MinValueValidator(100), validators.MaxValueValidator(600)])

    content_check_string = models.CharField(
        max_length=255, blank=True,
        verbose_name=_("Check for string"),
        help_text=_("Optionally, you can check if the response contains a certain string"))


    def run_check(self):
        if not self.should_run_check():
            return

        # Initialize the log instance
        log = CheckLog(check=self)

        # Send check
        check_result = monitoring.check_http_header(self.target, self.status_code)

        if check_result['valid']:
            log.status_extra = check_result['status_code']

            if check_result['status_ok']:
                if self.content_check_string.strip():
                    check_result = monitoring.check_http_content(self.target, self.content_check_string.strip())
                    log.status = 0 if check_result['status_ok'] else 1
                else:
                    log.status = 0
            else:
                log.status = 1
        else:
            log.status = 2

        log.save()

    class Meta:
        verbose_name = _("http check")
        verbose_name_plural = _("http checks")


class DnsCheck(BaseCheck):

    target = models.CharField(
        max_length=255, blank=False,
        help_text=_("Should be a hostname"),
        validators=[validate_hostname])

    resolved_address = models.CharField(
        max_length=255, blank=False,
        help_text=_("Should be a valid IP"),
        validators=[validators.validate_ipv46_address])

    DNS_RECORD_TYPES = (
        ('A', 'A'),
        ('AAAA', 'AAAA'),
        ('CNAME', 'CNAME'),
        ('MX', 'MX'),
        ('TXT', 'TXT')
    )

    record_type = models.CharField(
        max_length=5,
        choices=DNS_RECORD_TYPES,
        default='A',
        help_text=_("Type of dns resource record"))

    def run_check(self):
        if not self.should_run_check():
            return

        check_result = monitoring.check_dns(target=self.target,
                                            expected_address=self.resolved_address,
                                            record_type=self.record_type)

        # Initialize the log instance
        log = CheckLog(check=self)

        if check_result['valid']:
            if check_result['status_ok']:
                log.status = 0
            else:
                log.status = 1
        else:
            log.status = 2

        log.save()

    class Meta:
        verbose_name = _("dns check")
        verbose_name_plural = _("dns checks")


CHECK_TYPES = [DnsCheck, PingCheck, PortCheck, HttpCheck]

###############################################################

class CheckGroup(models.Model):
    """Group of related checks"""
    title = models.CharField(max_length=65,
                             help_text=_("Title for the group of checks"))
    owner = models.ForeignKey(User)

    def __str__(self):
        return _("Check group") + " '" + self.title + "'"

    def checks(self):
        checks = list(chain(self.dnscheck_set.all(), self.pingcheck_set.all(), self.httpcheck_set.all(), self.portcheck_set.all()))

        return checks

    def enable(self):
        for check_type in CHECK_TYPES:
            check_type.objects.filter(group=self).update(is_active=True)

    def disable(self):
        for check_type in CHECK_TYPES:
            check_type.objects.filter(group=self).update(is_active=False)



###############################################################
# Generic Check List

# In order to have lists of checks regardless of their type
# I've created a 'CheckInList' model. One is created for each check.
# Creation and deletion of Check elements trigger the creation
# and deletion of CheckInList elements.

# from django.db.models.signals import post_save, post_delete

# class CheckInList(models.Model):
#     """Generic model to represent checks of any kind in a set of checks."""

#     content_type = models.ForeignKey(ContentType)
#     object_id = models.PositiveIntegerField()
#     check = generic.GenericForeignKey()

# def add_check(sender, **kwargs):
#     """Creates a CheckInList element for the newly generated Check"""

#     if 'created' in kwargs and kwargs['created']:
#         instance = kwargs['instance']
#         ctype = ContentType.objects.get_for_model(instance)
#         CheckInList.objects.get_or_create(content_type=ctype,
#                                           object_id=instance.id)

# def delete_check(sender, **kwargs):
#     """Deletes the CheckInList element associated to a recently deleted Check"""

#     instance = kwargs['instance']
#     object_id = instance.id
#     ctype = ContentType.objects.get_for_model(instance)

#     CheckInList.objects.get(object_id=object_id, content_type=ctype).delete()

# # Attachment of functions to triggers/signals
# check_types = [PortCheck, HttpCheck, DnsCheck, PingCheck]
# for check_type in check_types:
#     post_save.connect(add_check, sender=check_type)
#     post_delete.connect(delete_check, sender=check_type)