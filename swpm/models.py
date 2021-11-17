import datetime
from QuantLib.QuantLib import PiecewiseLogLinearDiscount
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import query_utils
from django.db.models.deletion import CASCADE, DO_NOTHING, SET_NULL, SET_DEFAULT
from django.db.models.fields.related import ForeignKey
from django.utils import timezone
from django.utils.translation import gettext as _
from django.core.exceptions import ValidationError
from django.core import validators
from django.core.validators import RegexValidator, MinValueValidator, DecimalValidator

import QuantLib as ql
import pandas as pd

FXO_TYPE = [("EUR", "European"), 
        ("AME", "American"), 
        ("DIG", "Digital"), 
        ("BAR", "Barrier")]
    
FXO_CP = [("C","Call"), ("P","Put")]

SWAP_PAY_REC = [(-1, "Receive"), (1, "Pay")]

BUY_SELL = [("B", "Buy"), ("S", "Sell")]

CHOICE_DAY_COUNTER = models.TextChoices('DAY_COUNTER', ['Actual360', 'Actual365Fixed', 'ActualActual', 'Thirty360'])
QL_DAY_COUNTER = {"Actual360": ql.Actual360(), 
                'Actual365Fixed': ql.Actual365Fixed(), 
                'ActualActual': ql.ActualActual(), 
                'Thirty360': ql.Thirty360()}

CHOICE_DAY_RULE = models.TextChoices('DAY_RULE', ['Following', 'ModifiedFollowing', 'Preceding', 'ModifiedPreceding', 'Unadjusted'])
QL_DAY_RULE = {'Following': ql.Following, 
            'ModifiedFollowing': ql.ModifiedFollowing, 
            'Preceding': ql.Preceding, 
            'ModifiedPreceding': ql.ModifiedPreceding, 
            'Unadjusted': ql.Unadjusted}

# https://docs.djangoproject.com/en/3.2/ref/models/fields/#enumeration-types

QL_CALENDAR = {'NullCalendar': ql.NullCalendar(),
                'TARGET': ql.TARGET(), 
                'UnitedStates': ql.UnitedStates(), 
                'HongKong': ql.HongKong(), 
                'UnitedKingdom': ql.UnitedKingdom()
                }

def validate_positive(value):
    if value <= 0:
        raise ValidationError(_('Amount must be positive'), code='non_positive')
        
# class PositiveFloatField(models.Field):
#     default_validators = [validate_positive]
#     def validate(self, value):
#         super().validate(value)

def to_qlDate(d: datetime.date) -> ql.Date:
    return ql.Date(d.isoformat(),'%Y-%m-%d')

class User(AbstractUser):
    pass

class Calendar(models.Model):
    name = models.CharField(max_length=16)
    def __str__(self):
        return self.name
    def calendar(self):
        return QL_CALENDAR[self.name]

class Ccy(models.Model):
    code = models.CharField(max_length=3, blank=False, primary_key=True)
    fixing_days = models.PositiveIntegerField(default=2)
    cdr = models.ForeignKey(Calendar, DO_NOTHING, related_name="ccys", null=True)
    risk_free_curve = models.CharField(max_length=16, blank=True, null=True) #free text
    foreign_exchange_curve = models.CharField(max_length=16, blank=True, null=True) #free text
    def __str__(self):
        return self.code

class CcyPair(models.Model):
    name = models.CharField(max_length=7, primary_key=True)
    base_ccy = models.ForeignKey(Ccy, CASCADE, related_name="as_base_ccy")
    quote_ccy = models.ForeignKey(Ccy, CASCADE, related_name="as_quote_ccy")
    cdr = models.ForeignKey(Calendar, DO_NOTHING, related_name="ccy_pairs", null=True)
    fixing_days = models.PositiveIntegerField(default=2)
    def check_order():
        # check correct order
        return True
    def __str__(self):
        return f"{self.base_ccy}/{self.quote_ccy}"
    def get_rate(self, date):
        return self.rates.get(ref_date=date)
    def calendar(self):
        return self.cdr.calendar()

class FxSpotRateQuote(models.Model):
    ref_date = models.DateField()
    rate = models.FloatField()
    ccy_pair = models.ForeignKey(CcyPair, CASCADE, related_name="rates")
    class Meta:
        unique_together = ('ref_date', 'ccy_pair')
    def handle(self):
        return ql.QuoteHandle(ql.SimpleQuote(self.rate))
    def __str__(self):
        return f"{self.ccy_pair}: {self.rate} as of {self.ref_date}"
    
class RateQuote(models.Model):
    name = models.CharField(max_length=16)
    ref_date = models.DateField()
    rate = models.FloatField()
    tenor = models.CharField(max_length=5)
    instrument = models.CharField(max_length=5)
    ccy = models.ForeignKey(Ccy, CASCADE, related_name="rates")
    day_counter = models.CharField(max_length=16, choices=CHOICE_DAY_COUNTER.choices)
    #index = models.ForeignKey(RateIndex, DO_NOTHING, null=True, blank=True) # RateIndex is not defined yet above this model
    def helper(self):
        q = ql.QuoteHandle(ql.SimpleQuote(self.rate))
        tenor_ = None if self.instrument == "FUT" else ql.Period(self.tenor) 
        if self.instrument == "DEPO":
            fixing_days = self.ccy.fixing_days
            convention = ql.ModifiedFollowing
            ccy = Ccy.objects.get(code=self.ccy) #not used yet
            return ql.DepositRateHelper(self.rate, tenor_, fixing_days, ql.TARGET(), convention, False, QL_DAY_COUNTER[self.day_counter])
        elif self.instrument == "FUT":
            if self.tenor[:2] == 'ED':
                return ql.FuturesRateHelper(q, ql.IMM.date(self.tenor[2:4]), ql.USDLibor(ql.Period('3M')))
        elif self.instrument == "SWAP":
            if self.ccy.code == "USD":
                swapIndex = ql.UsdLiborSwapIsdaFixAm(tenor_)
                return ql.SwapRateHelper(q, swapIndex)
        elif self.instrument == "OIS":
            overnight_index = ql.OvernightIndex('USD EFFR', 0, ql.USDCurrency(), ql.UnitedStates(), ql.Actual365Fixed())
            if self.ccy.code == "USD":
                if self.tenor == '1D':
                    return ql.DepositRateHelper(q, overnight_index)
                else:
                    swapIndex = ql.OvernightIndexedSwapIndex("EFFR", tenor_, 2, ql.USDCurrency(), overnight_index)
                    return ql.OISRateHelper(2, tenor_, q, overnight_index)
    def __str__(self):
        return f"{self.name}: ({self.ccy}) as of {self.ref_date}: {self.rate}"

class IRTermStructure(models.Model):
    name = models.CharField(max_length=16)
    ref_date = models.DateField()
    ccy = models.ForeignKey(Ccy, CASCADE, related_name="all_curves", null=True, blank=True)
    rates = models.ManyToManyField(RateQuote, related_name="ts")
    as_fx_curve = models.ForeignKey(Ccy, CASCADE, related_name="fx_curve", null=True)
    as_rf_curve = models.ForeignKey(Ccy, CASCADE, related_name="rf_curve", null=True)
    class Meta:
        unique_together = ('name', 'ref_date', 'ccy')
    def term_structure(self):
        day_counter = ql.Actual365Fixed()
        helpers = [rate.helper() for rate in self.rates.all()]
        yts = ql.PiecewiseLogLinearDiscount(to_qlDate(self.ref_date), helpers, day_counter)
        yts.enableExtrapolation()
        return yts
    def __str__(self):
        return f"{self.name} as of {self.ref_date}"

class RateIndex(models.Model):
    name = models.CharField(max_length=16, primary_key=True)
    ccy = models.ForeignKey(Ccy, CASCADE, related_name="rate_indexes")
    index = models.CharField(max_length=16)
    tenor = models.CharField(max_length=16)
    day_counter = models.CharField(max_length=16, choices=CHOICE_DAY_COUNTER.choices, null=True, blank=True)
    yts = models.CharField(max_length=16, null=True, blank=True)
    class Meta:
        unique_together = ('name', 'tenor')
    def __str__(self):
        return self.name
    def get_index(self, ref_date=None, eff_date=None):
        if 'USD LIBOR' in self.name:
            idx_cls = ql.USDLibor
        elif 'USD EFFR' in self.name:
            idx_cls = ql.OvernightIndex

        if ref_date:
                yts = IRTermStructure.objects.get(name=self.yts, ref_date=ref_date).term_structure()

        if 'USD LIBOR' in self.name:
            if yts:
                idx_obj = idx_cls(ql.Period(self.tenor), ql.YieldTermStructureHandle(yts))
            else:
                idx_obj = idx_cls(ql.Period(self.tenor))
        elif 'USD EFFR' in self.name:
            if yts:
                idx_obj = idx_cls('USD EFFR', 1, ql.USDCurrency(), ql.Actual365Fixed(), ql.YieldTermStructureHandle(yts))
            else:
                idx_obj = idx_cls('USD EFFR', 1, ql.USDCurrency(), ql.Actual365Fixed())

        if eff_date:
            first_fixing_date = idx_obj.fixingDate(to_qlDate(eff_date))
            for f in self.fixings.filter(ref_date__gte=first_fixing_date.ISO()):
                idx_obj.addFixings([to_qlDate(f.ref_date)], [f.value])
        
        return idx_obj

class RateIndexFixing(models.Model):
    value = models.FloatField()
    index = models.ForeignKey(RateIndex, CASCADE, related_name="fixings")
    ref_date = models.DateField()
    class Meta:
        unique_together = ('ref_date', 'index')
    def __str__(self):
        return f'{self.index} on {self.ref_date}'

class FXVolatility(models.Model):
    ref_date = models.DateField()
    ccy_pair = models.ForeignKey(CcyPair, CASCADE, related_name='vol')
    vol = models.FloatField()
    class Meta:
        verbose_name_plural = "FX volatilities"
    def handle(self):
        return ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(to_qlDate(self.ref_date), self.ccy_pair.calendar(), self.vol, ql.Actual365Fixed()))
    def __str__(self):
        return f"{self.ccy_pair} as of {self.ref_date}"
    
class FXOManager(models.Manager):
    def create_fxo(self, trade_date, maturity_date, ccy_pair, strike_price, type, cp, notional_1):
        fxo = self.create(
            trade_date = trade_date, 
            maturity_date = maturity_date, 
            ccy_pair = ccy_pair, 
            strike_price = strike_price, 
            type = type, 
            cp = cp, 
            notional_1 = notional_1, 
            notional_2 = notional_1 * strike_price
        )
        return fxo

class Portfolio(models.Model):
    name = models.CharField(max_length=16, primary_key=True)
    def __str__(self) -> str:
        return self.name


class Book(models.Model):
    name = models.CharField(max_length=16, primary_key=True)
    portfolio = models.ForeignKey(Portfolio, DO_NOTHING, related_name="books")
    owner = models.ForeignKey(User, DO_NOTHING, null=True, related_name="books")
    def __str__(self) -> str:
        return self.name

class Counterparty(models.Model):
    code = models.CharField(max_length=16, primary_key=True)
    name = models.CharField(max_length=64)
    is_internal = models.OneToOneField(Book, DO_NOTHING, null=True, blank=True, related_name="internal_cpty")
    class Meta:
        verbose_name_plural = "Counterparties"
    def __str__(self) -> str:
        return self.name
    
class TradeDetail(models.Model):
    #trade = models.ForeignKey(FXO, CASCADE, related_name="detail")
    def __str__(self) -> str:
        return f"ID: {self.trade.id}"

class TradeMarkToMarket(models.Model):
    as_of = models.DateField()
    trade_d = models.ForeignKey(TradeDetail, CASCADE, null=True, related_name="mtms")
    npv = models.FloatField(null=True)
    delta = models.FloatField(null=True)
    gamma = models.FloatField(null=True)
    vega = models.FloatField(null=True)
    class Meta:
        unique_together = ('as_of', 'trade_d')
    def __str__(self):
        return f"Trade {self.trade_d.trade.first().id} NPV={self.npv:.2f} as of {self.as_of}"

class Trade(models.Model):
    id = models.BigAutoField(primary_key=True)
    active = models.BooleanField(default=True)
    create_time = models.DateTimeField(auto_now_add=True)
    trade_date = models.DateField(null=False)
    detail = models.OneToOneField(TradeDetail, CASCADE, null=True, related_name="trade")
    
    book = models.ForeignKey(Book, SET_NULL, null=True, blank=True, related_name="trades")
    input_user = models.ForeignKey(User, SET_NULL, null=True, related_name='input_trades')
    counterparty = models.ForeignKey(Counterparty, DO_NOTHING, related_name="trade_set", null=True, blank=True)
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.detail:
             self.detail.delete()
         
    #class Meta:
        #abstract = True
        #ordering = ['id']
    # def save(self, *args, **kwargs):
    #     if self.detail == None:
    #         d = TradeDetail.objects.create()
    #         d.save()
    #         self.detail = d
    #     super().save(*args, **kwargs)

        

class FXO(Trade):
    product_type = models.CharField(max_length=12, default="FXO")
    maturity_date = models.DateField(null=False, default=datetime.date.today())
    buy_sell = models.CharField(max_length=1, choices=BUY_SELL)
    ccy_pair = models.ForeignKey(CcyPair, models.DO_NOTHING, null=False, related_name='options')
    strike_price = models.FloatField(validators=[validate_positive])
    notional_1 = models.FloatField(validators=[validate_positive])
    notional_2 = models.FloatField(validators=[validate_positive])
    type = models.CharField(max_length=5, choices=FXO_TYPE)
    cp = models.CharField(max_length=1, choices=FXO_CP)
    objects = FXOManager()

    def __str__(self):
        return f"FXO ID: {self.id}, {self.ccy_pair}, Notional={self.notional_1:.0f}, K={self.strike_price}"
    
    def save(self, *args, **kwargs):
        if self.notional_2 == None:
            self.notional_2 = self.notional_1 * self.strike_price
        super().save(*args, **kwargs)
    
    def instrument(self):
        cp = ql.Option.Call if self.cp=="C" else ql.Option.Put
        if self.type == 'EUR':
            payoff = ql.PlainVanillaPayoff(cp, self.strike_price)
        elif self.type == 'DIG':
            payoff = ql.CashOrNothingPayoff(cp, self.strike_price, 1.0)
        else:
            payoff = ql.PlainVanillaPayoff(cp, self.strike_price)
        exercise = ql.EuropeanExercise(to_qlDate(self.maturity_date))
        inst = ql.VanillaOption(payoff, exercise)
        return inst

    def make_pricing_engine(self, as_of):
        if self.active:
            spot_rate = self.ccy_pair.rates.get(ref_date=as_of)
            v = self.ccy_pair.vol.get(ref_date=as_of).handle()
            q = IRTermStructure.objects.get(ref_date=as_of, as_fx_curve=self.ccy_pair.base_ccy).term_structure()
            r = IRTermStructure.objects.get(ref_date=as_of, as_fx_curve=self.ccy_pair.quote_ccy).term_structure()
            process = ql.BlackScholesMertonProcess(spot_rate.handle(), ql.YieldTermStructureHandle(q), ql.YieldTermStructureHandle(r), v)
            return ql.AnalyticEuropeanEngine(process)


#class SwapManager():
#    pass

class Swap(Trade):
    #objects = SwapManager()
    product_type = models.CharField(max_length=12, default="SWAP")
    maturity_date = models.DateField(null=True, blank=True)
    def instrument(self, as_of):
        legs = [x.leg(as_of=as_of) for x in self.legs.all()] #maybe need to use x.leg(as_of=xxxxx)
        is_pay = [leg.pay_rec>0 for leg in self.legs.all()]
        return ql.Swap(legs, is_pay)
    def make_pricing_engine(self, as_of):
        leg = self.legs.get(pay_rec=-1)
        yts1 = leg.ccy.rf_curve.get(ref_date=as_of).term_structure()
        return ql.DiscountingSwapEngine(ql.YieldTermStructureHandle(yts1))
    def __str__(self):
        return f"Swap ID: {self.id}, Notional={self.legs.first().notional:.0f} & {self.legs.last().notional:.0f}"
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        if self.detail:
             self.detail.delete()

class SwapLeg(models.Model):
    trade = models.ForeignKey(Swap, CASCADE, null=True, blank=True, related_name="legs")
    ccy = models.ForeignKey(Ccy, CASCADE, related_name="swap_legs")
    effective_date = models.DateField(default=datetime.date.today())
    maturity_date = models.DateField()
    notional = models.FloatField(default=1e6, validators=[validate_positive])
    pay_rec = models.IntegerField(choices=SWAP_PAY_REC)
    fixed_rate = models.FloatField(null=True, blank=True)
    index = models.ForeignKey(RateIndex, SET_NULL, null=True, blank=True)
    spread = models.FloatField(null=True, blank=True)
    reset_freq = models.CharField(max_length=16, validators=[RegexValidator], null=True, blank=True)
    payment_freq = models.CharField(max_length=16, validators=[RegexValidator])
    calendar = models.ForeignKey(Calendar, SET_DEFAULT, default=ql.NullCalendar())
    day_counter = models.CharField(max_length=16, choices=CHOICE_DAY_COUNTER.choices)
    day_rule = models.CharField(max_length=24, choices=CHOICE_DAY_RULE.choices, default='ModifiedFollowing')
    def get_schedule(self):
        return ql.MakeSchedule(to_qlDate(self.effective_date), 
                            to_qlDate(self.maturity_date), 
                            ql.Period(self.payment_freq), 
                            calendar=self.calendar.calendar())
    def leg(self, as_of):
        sch = self.get_schedule()
        dc = QL_DAY_COUNTER[self.day_counter]
        day_rule = QL_DAY_RULE[self.day_rule]
        if self.index:
            leg_idx = self.index.get_index(ref_date=as_of, eff_date=self.effective_date) # need to fix
            if 'IBOR' in self.index.name:
                leg = ql.IborLeg([self.notional], sch, leg_idx, dc, 
                            paymentConvention=day_rule,
                            fixingDays=[leg_idx.fixingDays()], 
                            spreads=[float(self.spread or 0.0)])
                # temp=pd.DataFrame([{
                # 'fixingDate': cf.fixingDate().ISO(),
                # 'accrualStart': cf.accrualStartDate().ISO(),
                # 'accrualEnd': cf.accrualEndDate().ISO(),
                # "paymentDate": cf.date().ISO(),
                # 'gearing': cf.gearing(),
                # 'forward': cf.indexFixing(),
                # 'rate': cf.rate(),
                # "amount": cf.amount()
                # } for cf in leg])
            elif 'OIS' in self.index.name:
                leg = ql.OvernightLeg([self.notional], sch, leg_idx, dc, 
                                        BusinessDayConvention=self.day_rule,
                                        gearing=[1],
                                        spread=self.spread,
                                        TelescopicValueDates=True)
            else:
                pass # other floating leg
        else: # self.index==None
            leg = ql.FixedRateLeg(sch, QL_DAY_COUNTER[self.day_counter], [self.notional], [self.fixed_rate*0.01])

        return leg
    def make_pricing_engine(self, as_of):
        discount_curve = self.ccy.rf_curve.get(ref_date=as_of).term_structure()
        return ql.DiscountingSwapEngine(ql.YieldTermStructureHandle(discount_curve))

