import re
from datetime import datetime

from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.db.models.signals import post_save, post_delete
from django.core import validators

from siteup_checker import monitoring
from .validators import ValidateAnyOf

# Base models

class BaseCheck(models.Model):
    """Base model for the checks. It groups the common fields and relations.
    It's an abstract base class, so no actual table is created for this model."""

    owner = models.ForeignKey(User, null=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    target = models.TextField(blank=False)
    check_interval = models.PositiveSmallIntegerField(default=1)
    notify_email = models.BooleanField(default=True)

    logs = generic.GenericRelation('CheckLog')
    last_log_datetime = models.DateTimeField(auto_now_add=True, blank=True)

    def should_run_check(self):
        if not self.is_active:
            print "Check won't run: it's not active"
            return False

        time_since_last = datetime.now() - self.last_log_datetime
        if time_since_last.seconds < self.check_interval * 60 - 1:
            print "Check won't run: not enough time has passed"
            return False

        print "Check will run"
        return True

    class Meta:
        abstract = True

class CheckInList(models.Model):
    """Generic model to represent checks of any kind in a set of checks."""

    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    check = generic.GenericForeignKey()

class CheckLog(models.Model):
    """Stores the result of the check."""

    date = models.DateTimeField(auto_now_add=True)
    is_ok = models.BooleanField(default=True)
    value = models.CharField(max_length=255, blank=True)
    extra = models.TextField(blank=True)
    is_notified = models.BooleanField(default=False)

    # Generic relation to the logged check
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    check = generic.GenericForeignKey()

    # Update parent's last_log_datetime
    def save(self, *args, **kwargs):
        print "Setting date:", self.date
        self.check.last_log_datetime = datetime.now()
        self.check.save()

        super(CheckLog, self).save(*args, **kwargs)


# Concrete models

class PingCheck(BaseCheck):
    should_check_timeout = models.BooleanField(default=False)
    timeout_value = models.PositiveSmallIntegerField(null=True, blank=True,
        validators=[ValidateAnyOf(validators.MaxValueValidator(10),
                                  validators.MinValueValidator(100))])

    def clean(self):
        target_ok = False

        try:
            # Check if it's an IP
            validators.validate_ipv46_address(self.target)
            target_ok = True
        except:
            # Check if it's a hostname
            hostname_regex = "^(([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]*[a-zA-Z0-9])\.)*([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9\-]*[A-Za-z0-9])$";
            target_ok = re.match(hostname_regex, self.target)

        if not target_ok:
            raise ValidationError('Target should be an IP or a valid hostname')


    def run_check(self):
        if not self.should_run_check():
            return

        # Initialize the log instance
        log = CheckLog(check=self, is_ok=True)

        # Fire the ping
        check_result = monitoring.check_ping(self.target)

        # Ping properly finished
        if check_result['valid']:

            # Save ping average response time
            log.value = check_result['avg']

            # If most pings were received
            if check_result['received'] / check_result['transmitted'] >= 0.5:

                # Check if response time is within boundaries
                if self.should_check_timeout and int(check_result['avg']) > self.timeout_value:
                    log.is_ok = False
                    log.extra = 'Ping max response time exceeded'

            else:
                log.is_ok = False

        # Ping could not be launched
        else:
            log.is_ok = False
            log.extra = 'Incorrect host'

        log.save()
        print log.id


class PortCheck(BaseCheck):
    target_port = models.PositiveSmallIntegerField()
    should_check_response = models.BooleanField(default=False)
    response_value = models.CharField(max_length=255, blank=True)


    def run_check(self):
        if not self.should_run_check():
            return

        # TO BE IMPLEMENTED


class HttpCheck(BaseCheck):
    should_check_status = models.BooleanField(default=True)
    status_value = models.PositiveSmallIntegerField(null=True,
                                                    blank=True,
                                                    validators=[validators.MinValueValidator(100),
                                                                validators.MaxValueValidator(600)])

    should_check_content = models.BooleanField(default=False)
    content_value = models.CharField(max_length=255, blank=True)


    def run_check(self):
        if not self.should_run_check():
            return

        # Initialize the log instance
        log = CheckLog(check=self)

        # Check for 404 by default
        status_code = self.status_value if self.should_check_status else 404

        # Send check
        check_result = monitoring.check_http_header(self.target, status_code)

        if check_result['valid']:
            log.value = check_result['status_code']
            log.is_ok = check_result['status_ok']
        else:
            log.is_ok = False

        log.save()

class DnsCheck(BaseCheck):
    resolved_address = models.CharField(max_length=255)
    register_type = models.CharField(max_length=20)

    def run_check(self):
        if not self.should_run_check():
            return

        check_result = monitoring.check_dns(self.target, self.resolved_address, self.register_type)

        # Initialize the log instance
        log = CheckLog(check=self, is_ok=check_result)
        log.save()

# Signal handlers

# In order to have lists of checks regardless of their type
# I've created a 'CheckInList' model. One is created for each check.
# Creation and deletion of Check elements trigger the creation
# and deletion of CheckInList elements.

def add_check(sender, **kwargs):
    """Creates a CheckInList element for the newly generated Check"""

    if 'created' in kwargs and kwargs['created']:
        instance = kwargs['instance']
        ctype = ContentType.objects.get_for_model(instance)
        CheckInList.objects.get_or_create(content_type=ctype,
                                          object_id=instance.id)

def delete_check(sender, **kwargs):
    """Deletes the CheckInList element associated to a recently deleted Check"""

    instance = kwargs['instance']
    object_id = instance.id
    ctype = ContentType.objects.get_for_model(instance)

    CheckInList.objects.get(object_id=object_id, content_type=ctype).delete()

# Attachment of functions to triggers/signals
check_types = [PortCheck, HttpCheck, DnsCheck, PingCheck]
for check_type in check_types:
    post_save.connect(add_check, sender=check_type)
    post_delete.connect(delete_check, sender=check_type)