import datetime
from decimal import Decimal

from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import crypto, timezone
from django.utils.translation import gettext_lazy as _
from django_hosts.resolvers import reverse
from sorl.thumbnail import ImageField

from djangoproject.thumbnails import LogoThumbnailMixin

GOAL_AMOUNT = Decimal("300000.00")
GOAL_START_DATE = datetime.date(datetime.datetime.today().year, 1, 1)
DISPLAY_DONOR_DAYS = 365
DEFAULT_DONATION_AMOUNT = 50
LEADERSHIP_LEVEL_AMOUNT = Decimal("1000.00")
INTERVAL_CHOICES = (
    ("monthly", _("Monthly donation")),
    ("quarterly", _("Quarterly donation")),
    ("yearly", _("Yearly donation")),
    ("onetime", _("One-time donation")),
)


class DjangoHeroManager(models.Manager):
    def for_public_display(self):
        donors = (
            self.get_queryset()
            .filter(
                is_visible=True,
                approved=True,
                donation__payment__date__gt=datetime.date.today()
                - datetime.timedelta(days=DISPLAY_DONOR_DAYS),
            )
            .annotate(donated_amount=models.Sum("donation__payment__amount"))
        )
        return donors.order_by("-donated_amount", "name")


def get_fundraising_id():
    return crypto.get_random_string(length=12)


class FundraisingModel(models.Model):
    id = models.CharField(max_length=12, primary_key=True)
    created = models.DateTimeField(default=timezone.now)
    modified = models.DateTimeField(default=timezone.now)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.modified = timezone.now()
        if not self.id:
            self.id = get_fundraising_id()
        return super().save(*args, **kwargs)


class DjangoHero(LogoThumbnailMixin, FundraisingModel):
    email = models.EmailField(blank=True)
    # TODO: Make this unique.
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    logo = ImageField(upload_to="fundraising/logos/", blank=True)
    url = models.URLField(blank=True, verbose_name="URL")
    name = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=255, blank=True)
    HERO_TYPE_CHOICES = (
        ("individual", _("Individual")),
        ("organization", _("Organization")),
    )
    hero_type = models.CharField(max_length=30, choices=HERO_TYPE_CHOICES, blank=True)
    is_visible = models.BooleanField(
        default=False,
        verbose_name=_("Agreed to displaying on the fundraising page?"),
    )
    is_subscribed = models.BooleanField(
        default=False,
        verbose_name=_("Agreed to being contacted by DSF?"),
    )
    approved = models.BooleanField(
        null=True,
        verbose_name=_("Name, URL, and Logo approved?"),
    )

    objects = DjangoHeroManager()

    def __str__(self):
        return self.name if self.name else f"Anonymous #{self.pk}"

    class Meta:
        verbose_name = _("Django hero")
        verbose_name_plural = _("Django heroes")

    @property
    def display_name(self):
        return self.name

    @property
    def name_with_fallback(self):
        return self.name if self.name else _("Anonymous Hero")


class Donation(FundraisingModel):
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, blank=True)
    subscription_amount = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True
    )
    donor = models.ForeignKey(DjangoHero, on_delete=models.CASCADE)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)
    stripe_customer_id = models.CharField(max_length=100, blank=True)
    receipt_email = models.EmailField(blank=True)

    def __str__(self):
        return f"{self.get_interval_display()} from {self.donor}"

    def get_absolute_url(self):
        return reverse("fundraising:thank-you", kwargs={"donation": self.id})

    def is_active(self):
        return bool(self.stripe_subscription_id)

    is_active.boolean = True

    def total_payments(self):
        return self.payment_set.aggregate(models.Sum("amount"))["amount__sum"]


class Payment(models.Model):
    donation = models.ForeignKey(Donation, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=9, decimal_places=2, null=True)
    stripe_charge_id = models.CharField(max_length=100, unique=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"${self.amount}"


class Testimonial(models.Model):
    author = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.author


class InKindDonor(LogoThumbnailMixin, models.Model):
    name = models.CharField(max_length=100)
    url = models.URLField(blank=True, verbose_name="URL")
    description = models.TextField()
    logo = ImageField(upload_to="fundraising/logos/", blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("in-kind hero")
        verbose_name_plural = _("in-kind heroes")

    @property
    def display_name(self):
        return self.name


@receiver(post_save, sender=DjangoHero)
@receiver(post_save, sender=InKindDonor)
def create_thumbnail_on_save(sender, **kwargs):
    return kwargs["instance"].thumbnail
