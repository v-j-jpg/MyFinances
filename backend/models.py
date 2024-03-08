from uuid import uuid4

from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import UserManager, AbstractUser, AnonymousUser
from django.db import models
from django.db.models import Count
from django.utils import timezone
from django.utils.crypto import get_random_string
from shortuuid.django_fields import ShortUUIDField

from settings import settings
from settings.settings import AWS_TAGS_APP_NAME


def RandomCode(length=6):
    return get_random_string(length=length).upper()


def RandomAPICode(length=89):
    return get_random_string(length=length).lower()


def USER_OR_ORGANIZATION_CONSTRAINT():
    return models.CheckConstraint(
        name=f"%(app_label)s_%(class)s_check_user_or_organization",
        check=(models.Q(user__isnull=True, organization__isnull=False) | models.Q(user__isnull=False, organization__isnull=True)),
    )


class CustomUserManager(UserManager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("user_profile", "logged_in_as_team")
            .annotate(notification_count=((Count("user_notifications"))))
        )


class User(AbstractUser):
    objects = CustomUserManager()

    logged_in_as_team = models.ForeignKey("Team", on_delete=models.SET_NULL, null=True)
    awaiting_email_verification = models.BooleanField(default=True)

    class Role(models.TextChoices):
        #        NAME     DJANGO ADMIN NAME
        DEV = "DEV", "Developer"
        STAFF = "STAFF", "Staff"
        USER = "USER", "User"
        TESTER = "TESTER", "Tester"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)


class CustomUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Replace request.user with CustomUser instance if authenticated
        if request.user.is_authenticated:
            request.user = User.objects.get(pk=request.user.pk)
        else:
            # If user is not authenticated, set request.user to AnonymousUser
            request.user = AnonymousUser()

        response = self.get_response(request)
        return response


def add_3hrs_from_now():
    return timezone.now() + timezone.timedelta(hours=3)


class VerificationCodes(models.Model):
    class ServiceTypes(models.TextChoices):
        CREATE_ACCOUNT = "create_account", "Create Account"
        RESET_PASSWORD = "reset_password", "Reset Password"

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)  # This is the public identifier
    token = models.TextField(default=RandomCode, editable=False)  # This is the private token (should be hashed)

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    expiry = models.DateTimeField(default=add_3hrs_from_now)
    service = models.CharField(max_length=14, choices=ServiceTypes.choices)

    def __str__(self):
        return self.user.username

    def is_expired(self):
        if timezone.now() > self.expiry:
            self.delete()
            return True
        return False

    def hash_token(self):
        self.token = make_password(self.token)
        self.save()
        return True

    class Meta:
        verbose_name = "Verification Code"
        verbose_name_plural = "Verification Codes"


class UserSettings(models.Model):
    CURRENCIES = {
        "GBP": {"name": "British Pound Sterling", "symbol": "£"},
        "EUR": {"name": "Euro", "symbol": "€"},
        "USD": {"name": "United States Dollar", "symbol": "$"},
        "JPY": {"name": "Japanese Yen", "symbol": "¥"},
        "INR": {"name": "Indian Rupee", "symbol": "₹"},
        "AUD": {"name": "Australian Dollar", "symbol": "$"},
        "CAD": {"name": "Canadian Dollar", "symbol": "$"},
    }
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_profile")
    dark_mode = models.BooleanField(default=True)
    currency = models.CharField(
        max_length=3,
        default="GBP",
        choices=[(code, info["name"]) for code, info in CURRENCIES.items()],
    )
    profile_picture = models.ImageField(
        upload_to="profile_pictures/",
        storage=settings.CustomPublicMediaStorage(),
        blank=True,
        null=True,
    )

    @property
    def profile_picture_url(self):
        if self.profile_picture and hasattr(self.profile_picture, "url"):
            return self.profile_picture.url
        return ""

    def get_currency_symbol(self):
        return self.CURRENCIES.get(self.currency, {}).get("symbol", "$")

    def __str__(self):
        return self.user.username

    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"


class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    leader = models.ForeignKey(User, on_delete=models.CASCADE, related_name="teams_leader_of")
    members = models.ManyToManyField(User, related_name="teams_joined")


class TeamInvitation(models.Model):
    code = models.CharField(max_length=10)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team_invitations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="team_invitations")
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE)
    expires = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    def is_active(self):
        if not self.active:
            return False
        if timezone.now() > self.expires:
            self.active = False
            self.save()
            return False
        return True

    def set_expires(self):
        self.expires = timezone.now() + timezone.timedelta(days=7)

    def save(self, *args, **kwargs):
        self.set_expires()
        self.code = RandomCode(10)
        super().save()

    def __str__(self):
        return self.team.name

    class Meta:
        verbose_name = "Team Invitation"
        verbose_name_plural = "Team Invitations"


class Receipt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    organization = models.ForeignKey(Team, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to="receipts", storage=settings.CustomPrivateMediaStorage())
    total_price = models.FloatField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    date_uploaded = models.DateTimeField(auto_now_add=True)
    receipt_parsed = models.JSONField(null=True, blank=True)
    merchant_store = models.CharField(max_length=255, blank=True, null=True)
    purchase_category = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        constraints = [USER_OR_ORGANIZATION_CONSTRAINT()]


class ReceiptDownloadToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.ForeignKey(Receipt, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid4, editable=False, unique=True)


class Client(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    organization = models.ForeignKey(Team, on_delete=models.CASCADE, null=True)
    active = models.BooleanField(default=True)

    name = models.CharField(max_length=64)
    phone_number = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    company = models.CharField(max_length=100, blank=True, null=True)
    is_representative = models.BooleanField(default=False)

    address = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        constraints = [USER_OR_ORGANIZATION_CONSTRAINT()]

    def __str__(self):
        return self.name


class InvoiceProduct(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=100)
    quantity = models.IntegerField()
    rate = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)


class InvoiceItem(models.Model):
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=100)
    is_service = models.BooleanField(default=True)
    # if service
    hours = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    price_per_hour = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    # if product
    price = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)

    def get_total_price(self):
        if self.is_service:
            return self.hours * self.price_per_hour
        else:
            return self.price

    def __str__(self):
        return self.description


class Invoice(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    organization = models.ForeignKey(Team, on_delete=models.CASCADE, null=True)
    invoice_id = models.IntegerField(unique=True, blank=True, null=True)  # todo: add

    client_to = models.ForeignKey(Client, on_delete=models.SET_NULL, blank=True, null=True)

    client_name = models.CharField(max_length=100, blank=True, null=True)
    client_company = models.CharField(max_length=100, blank=True, null=True)
    client_address = models.CharField(max_length=100, blank=True, null=True)
    client_city = models.CharField(max_length=100, blank=True, null=True)
    client_county = models.CharField(max_length=100, blank=True, null=True)
    client_country = models.CharField(max_length=100, blank=True, null=True)
    client_is_representative = models.BooleanField(default=False)

    self_name = models.CharField(max_length=100, blank=True, null=True)
    self_company = models.CharField(max_length=100, blank=True, null=True)
    self_address = models.CharField(max_length=100, blank=True, null=True)
    self_city = models.CharField(max_length=100, blank=True, null=True)
    self_county = models.CharField(max_length=100, blank=True, null=True)
    self_country = models.CharField(max_length=100, blank=True, null=True)

    sort_code = models.CharField(max_length=8, blank=True, null=True)  # 12-34-56
    account_holder_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=100, blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    vat_number = models.CharField(max_length=100, blank=True, null=True)
    logo = models.ImageField(
        upload_to="invoice_logos",
        storage=settings.CustomPrivateMediaStorage(),
        blank=True,
        null=True,
    )
    notes = models.TextField(blank=True, null=True)

    payment_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    items = models.ManyToManyField(InvoiceItem)

    date_created = models.DateTimeField(auto_now_add=True)
    date_due = models.DateField()
    date_issued = models.DateField(blank=True, null=True)

    class Meta:
        constraints = [USER_OR_ORGANIZATION_CONSTRAINT()]

    @property
    def dynamic_payment_status(self):
        if self.date_due and timezone.now().date() > self.date_due and self.payment_status == "pending":
            return "overdue"
        else:
            return self.payment_status

    @property
    def get_to_details(self) -> tuple[str, dict[str, str]]:
        """
        Returns the client details for the invoice
        "client" and Client object if client_to
        "manual" and dict of details  if client_name
        """
        if self.client_to:
            return "client", self.client_to
        else:
            return "manual", {
                "name": self.client_name,
                "company": self.client_company,
            }

    def __str__(self):
        invoice_id = self.invoice_id or self.id
        if self.client_name:
            client = self.client_name
        elif self.client_to:
            client = self.client_to.name
        else:
            client = "Unknown Client"

        return f"Invoice #{invoice_id} for {client}"

    def get_subtotal(self):
        subtotal = 0
        for item in self.items.all():
            subtotal += item.get_total_price()
        return round(subtotal, 2)

    def get_total_price(self):
        total = 0
        subtotal = self.get_subtotal()
        if self.vat_number:
            total = subtotal * 1.2
        else:
            total = subtotal
        return round(total, 2)


class InvoiceURL(models.Model):
    uuid = ShortUUIDField(length=8, primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="invoice_urls")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_on = models.DateTimeField(auto_now_add=True)
    expires = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)

    def is_active(self):
        if not self.active:
            return False
        if timezone.now() > self.expires:
            self.active = False
            self.save()
            return False
        return True

    def set_expires(self):
        self.expires = timezone.now() + timezone.timedelta(days=7)

    def save(self, *args, **kwargs):
        self.set_expires()
        super().save()

    def __str__(self):
        return str(self.invoice.id)

    class Meta:
        verbose_name = "Invoice URL"
        verbose_name_plural = "Invoice URLs"


class InvoiceSchedule(models.Model):
    class StatusTypes(models.TextChoices):
        PENDING = "pending", "Pending"
        CREATING = "creating", "Creating"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        DELETING = "deleting", "Deleting"
        CANCELLED = "cancelled", "Cancelled"

    created_at = models.DateTimeField(auto_now_add=True)
    stored_schedule_arn = models.CharField(max_length=100, null=True, blank=True)
    received = models.BooleanField(default=False)
    status = models.CharField(max_length=100, choices=StatusTypes.choices, default=StatusTypes.PENDING)

    def get_tags(self):
        return {
            "invoice_id": self.invoice.id,
            "schedule_id": self.id,
            "app": AWS_TAGS_APP_NAME
        }

    class Meta:
        abstract = True


class InvoiceOnetimeSchedule(InvoiceSchedule):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="onetime_invoice_schedules")
    due = models.DateTimeField()

    class Meta:
        verbose_name = "One-Time Invoice Schedule"
        verbose_name_plural = "One-Time Invoice Schedules"


class APIKey(models.Model):
    class ServiceTypes(models.TextChoices):
        AWS_API_DESTINATION = "aws_api_destination"

    service = models.CharField(max_length=20, choices=ServiceTypes.choices, null=True)
    key = models.CharField(max_length=100, default=RandomAPICode)
    last_used = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API Key"
        verbose_name_plural = "API Keys"

    def __str__(self):
        return self.service

    def verify(self, key):
        return check_password(key, self.key)

    def hash(self):
        self.key = make_password(f"{self.id}{self.key}")
        self.save()




class PasswordSecret(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="password_secrets")
    secret = models.TextField(max_length=300)
    expires = models.DateTimeField(null=True, blank=True)


class Notification(models.Model):
    action_choices = [
        ("normal", "Normal"),
        ("modal", "Modal"),
        ("redirect", "Redirect"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_notifications")
    message = models.CharField(max_length=100)
    action = models.CharField(max_length=10, choices=action_choices, default="normal")
    action_value = models.CharField(max_length=100, null=True, blank=True)
    extra_type = models.CharField(max_length=100, null=True, blank=True)
    extra_value = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    organization = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.date}"


class LoginLog(models.Model):
    class ServiceTypes(models.TextChoices):
        MANUAL = "manual"
        MAGIC_LINK = "magic_link"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    service = models.CharField(max_length=14, choices=ServiceTypes.choices, default="manual")
    date = models.DateTimeField(auto_now_add=True)


class Error(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    error = models.CharField(max_length=250, null=True)
    error_code = models.CharField(max_length=100, null=True)
    error_colour = models.CharField(max_length=25, default="danger")
    date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.user_id)


class TracebackError(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    error = models.CharField(max_length=5000, null=True)
    date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.error)


class FeatureFlags(models.Model):
    name = models.CharField(max_length=100)
    value = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"
