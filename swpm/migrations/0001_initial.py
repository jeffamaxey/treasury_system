# Generated by Django 3.2.8 on 2021-10-31 06:41

from django.conf import settings
import django.contrib.auth.models
import django.contrib.auth.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='Calendar',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
            ],
        ),
        migrations.CreateModel(
            name='Ccy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=3)),
                ('fixing_days', models.PositiveIntegerField(default=2)),
                ('cdr', models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='ccys', to='swpm.calendar')),
            ],
        ),
        migrations.CreateModel(
            name='CcyPair',
            fields=[
                ('name', models.CharField(max_length=7, primary_key=True, serialize=False)),
                ('fixing_days', models.PositiveIntegerField(default=2)),
                ('base_ccy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='as_base_ccy', to='swpm.ccy')),
                ('cdr', models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='ccy_pairs', to='swpm.calendar')),
                ('quote_ccy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='as_quote_ccy', to='swpm.ccy')),
            ],
        ),
        migrations.CreateModel(
            name='FXO',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('active', models.BooleanField(default=True)),
                ('create_time', models.DateTimeField(auto_now_add=True)),
                ('trade_date', models.DateField()),
                ('maturity_date', models.DateField()),
                ('strike_price', models.FloatField()),
                ('notional_1', models.FloatField()),
                ('notional_2', models.FloatField()),
                ('type', models.CharField(choices=[('EUR', 'European'), ('AME', 'American'), ('DIG', 'Digital'), ('BAR', 'Barrier')], max_length=5)),
                ('cp', models.CharField(choices=[('C', 'Call'), ('P', 'Put')], max_length=1)),
                ('ccy_pair', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='options', to='swpm.ccypair')),
            ],
        ),
        migrations.CreateModel(
            name='Portfolio',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
            ],
        ),
        migrations.CreateModel(
            name='RateIndex',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
            ],
        ),
        migrations.CreateModel(
            name='TradeMarkToMarket',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('as_of', models.DateField()),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mtms', to='swpm.fxo')),
            ],
        ),
        migrations.CreateModel(
            name='TradeDetail',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='trades', to='swpm.portfolio')),
                ('input_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='input_trades', to=settings.AUTH_USER_MODEL)),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='detail', to='swpm.fxo')),
            ],
        ),
        migrations.CreateModel(
            name='RateQuote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
                ('rate', models.FloatField()),
                ('tenor', models.CharField(max_length=5)),
                ('instrument', models.CharField(max_length=5)),
                ('day_counter', models.CharField(max_length=16)),
                ('ccy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rates', to='swpm.ccy')),
            ],
        ),
        migrations.CreateModel(
            name='IRTermStructure',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
                ('ref_date', models.DateField()),
                ('as_fx_curve', models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='fx_curve', to='swpm.ccy')),
                ('as_rf_curve', models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='rf_curve', to='swpm.ccy')),
                ('rates', models.ManyToManyField(related_name='ts', to='swpm.RateQuote')),
            ],
        ),
        migrations.CreateModel(
            name='FXVolatility',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_date', models.DateField()),
                ('vol', models.FloatField()),
                ('ccy_pair', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vol', to='swpm.ccypair')),
            ],
            options={
                'verbose_name_plural': 'FX volatilities',
            },
        ),
        migrations.CreateModel(
            name='Book',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=16)),
                ('portfolio', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='books', to='swpm.portfolio')),
            ],
        ),
        migrations.CreateModel(
            name='FxSpotRateQuote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ref_date', models.DateField()),
                ('rate', models.FloatField()),
                ('ccy_pair', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rates', to='swpm.ccypair')),
            ],
            options={
                'unique_together': {('ref_date', 'ccy_pair')},
            },
        ),
    ]
