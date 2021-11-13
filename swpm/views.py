from django.contrib.auth import authenticate, login, logout
from django.db.models.query import RawQuerySet
from django.shortcuts import redirect, render
from django.db import IntegrityError
from django.http import *
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.serializers import serialize
from django.template import Context
from django.forms import modelformset_factory

from .models import *
from .forms import *
import datetime
import json
import pandas as pd

from dash import html
from dash import dcc
from django_plotly_dash import DjangoDash
import plotly.express as px

def str2date(s):
    if len(s) == 10:
        return datetime.datetime.strptime(s, '%Y-%m-%d')
    elif len(str(s)) == 8:
        return datetime.datetime.strptime(str(s), '%Y%m%d')

def index(request):
    mytime = timezone.now()
    myform = CcyPairForm()
    myFXOform = FXOForm(initial={'trade_date': datetime.date.today()})
    #trade_detail_form = TradeDetailForm()
    as_of_form = AsOfForm(initial={'as_of': datetime.date.today()})
    return render(request, "swpm/index.html", locals())


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)

        # Check if authentication successful
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "swpm/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "swpm/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST["email"]

        # Ensure password matches confirmation
        password = request.POST["password"]
        confirmation = request.POST["confirmation"]
        if password != confirmation:
            return render(request, "swpm/register.html", {"message": "Passwords must match."})

        # Attempt to create new user
        try:
            user = User.objects.create_user(username, email, password)
            user.save()
        except IntegrityError:
            return render(request, "swpm/register.html", {
                "message": "Username already taken."
            })
        login(request, user)
        return HttpResponseRedirect(reverse("index"))
    else:
        return render(request, "swpm/register.html")


def trade(request, **kwargs):
    as_of_form = AsOfForm(initial={'as_of': datetime.date.today()})
    valuation_message = kwargs.get('valuation_message')
    if kwargs['inst'] == "fxo":
        trade_type = "FX Option"
        val_form = FXOValuationForm()
        if kwargs.get('trade_form'):
            trade_form = kwargs['trade_form']
            as_of_form = kwargs['as_of_form']
            val_form = kwargs.get('val_form')
        else:
            trade_form = FXOForm(initial={'trade_date': datetime.date.today()})
    elif kwargs['inst'] == 'swap':
        trade_type = "Swap"
        if kwargs.get('trade_form'):
            swap_form = kwargs.get('trade_form')
            as_of_form = kwargs.get('as_of_form')
            trade_forms= kwargs.get('trade_forms')
            val_form = kwargs.get('val_form')
        else:
            SwapLegFormSet = modelformset_factory(SwapLeg, SwapLegForm, extra=2)
            trade_forms = SwapLegFormSet(queryset=SwapLeg.objects.none(), initial=[{'maturity_date': datetime.date.today()+datetime.timedelta(days=365)}])
            swap_form = SwapForm(initial={'trade_date': datetime.date.today()})
            val_form = SwapValuationForm()

    return render(request, "swpm/trade.html", locals())


@csrf_exempt
def trade_list(request):
    if request.method=='POST':
        form = TradeSearchForm(request.POST)
        form_ = dict([ (x[0], x[1]) for x in form.data.dict().items() if len(x[1])>0 ])
        trades1 = list(FXO.objects.filter(**form_).values())
        trades2 = list(Swap.objects.filter(**form_).values())
        search_result = trades1 + trades2
        return render(request, 'swpm/trade-list.html', {'form': TradeSearchForm(), "search_result": search_result})
    else:
        return render(request, 'swpm/trade-list.html', {'form': TradeSearchForm()})


@csrf_exempt
def pricing(request, commit=False):
    if request.method == 'POST':
        as_of = request.POST['as_of']
        as_of_form = AsOfForm(request.POST) #for render back to page
        ql.Settings.instance().evaluationDate = ql.Date(as_of,'%Y-%m-%d')
        valuation_message = None
        if request.POST['trade_type'] == 'FX Option':
            fxo_form = FXOForm(request.POST, instance=FXO())
            if fxo_form.is_valid():
                tr = fxo_form.save(commit=False)
                if commit and request.POST.get('book') and request.POST.get('counterparty'):
                    tr.input_user = request.user
                    tr.detail = TradeDetail.objects.create()
                    tr.save()
                    valuation_message = f"Trade is done, ID is {tr.id}."

                inst = tr.instrument()
                engine = tr.make_pricing_engine(as_of)
                inst.setPricingEngine(engine)
                side = 1.0 if tr.buy_sell=="B" else -1.0
                # will get full market data
                spot = tr.ccy_pair.rates.get(ref_date=as_of).rate
    
                result = {'npv': inst.NPV(), 
                            'delta': inst.delta(),
                            'gamma': inst.gamma()*0.01/spot,
                            'vega': inst.vega()*0.01, 
                            'theta': inst.thetaPerDay(), 
                            'rho': inst.rho()*0.01,
                            'dividendRho': inst.dividendRho()*0.01,
                            'itmCashProbability': inst.itmCashProbability()/side/tr.notional_1,
                            }
                result = dict([(x, round(y*side*tr.notional_1, 2)) for x, y in result.items()])
                valuation_form = FXOValuationForm(initial=result)
            else:
                valuation_form = FXOValuationForm()
            
            return trade(request, inst='fxo', trade_form=fxo_form, as_of_form=as_of_form, val_form=valuation_form, valuation_message=valuation_message)
        elif request.POST.get('trade_type') == 'Swap':
            SwapLegFormSet = modelformset_factory(SwapLeg, SwapLegForm, extra=2)
            swap_leg_form_set = SwapLegFormSet(request.POST)
            swap_form = SwapForm(request.POST, instance=Swap())
            if swap_form.is_valid() and swap_leg_form_set.is_valid():
                tr = swap_form.save(commit=False)
                legs = swap_leg_form_set.save(commit=False)
                if commit and request.POST.get('book') and request.POST.get('counterparty'):
                    tr.input_user = request.user
                    tr.detail = TradeDetail.objects.create()
                    tr.maturity_date = max([leg.maturity_date for leg in legs])
                    tr.save()
                    for leg in legs:
                        leg.trade = tr
                        leg.save()
                    valuation_message = f"Trade is done, ID is {tr.id}."
                    inst = tr.instrument(as_of)
                    engine = tr.make_pricing_engine(as_of)
                    inst.setPricingEngine(engine)
                else:
                    leg_inst = [x.leg(as_of=as_of) for x in legs]
                    is_pay = [leg.pay_rec>0 for leg in legs]
                    inst = ql.Swap(leg_inst, is_pay)
                    yts1 = legs[0].ccy.rf_curve.get(ref_date=as_of).term_structure()
                    inst.setPricingEngine(ql.DiscountingSwapEngine(yts1))
                    valuation_message = None
                result = {'npv': inst.NPV(), 'leg1bpv': inst.legBPS(0), 'leg2bpv': inst.legBPS(1)}
                result = dict([(x, round(y, 2)) for x, y in result.items()])
                #for leg
                valuation_form = SwapValuationForm(initial=result)
            else:
                return trade(request, inst='swap', trade_form=swap_form, as_of_form=as_of_form, trade_forms=swap_leg_form_set)
            return trade(request, inst='swap', trade_form=swap_form, as_of_form=as_of_form, trade_forms=swap_leg_form_set, 
                val_form=valuation_form, valuation_message=valuation_message)

@csrf_exempt                    
def save_ccypair(request):
    if request.method == 'POST':
        ccypair_obj = CcyPair()
        ccypair_form = CcyPairForm(request.POST, instance=ccypair_obj)
        if ccypair_form.is_valid():
            ccypair_form.save()
            return render(request, 'swpm/index.html', {"message": "saved successfully.", 'myform': ccypair_form})
    
@csrf_exempt   
def reval(request):
    if request.method == 'POST':
        reval_date = request.POST['reval_date']
        books = request.POST['books']
        if books:
            trades = TradeDetail.objects.none()
            for book in books:
                b = Book.objects.get(pk=book)
                trades = trades.union(b.trades.all())
        else:
            trades = TradeDetail.objects.all()

        for t in trades:
            inst = t.trade.first().instrument()
            engine = t.trade.first().make_pricing_engine(reval_date)
            inst.setPricingEngine(engine)
            side = 1.0 if t.trade.first().buy_sell=="B" else -1.0
            mtm, _ = TradeMarkToMarket.objects.get_or_create(as_of = reval_date, trade_d = t, defaults={'npv': side * inst.NPV() * t.trade.first().notional_1})
        return render(request, 'swpm/reval.html', {'reval_form': RevalForm(request.POST), 
                                                    'result': "Reval completed: \n" + str(TradeMarkToMarket.objects.filter(as_of=reval_date))
                                                    }
                    )
    else:
        return render(request, 'swpm/reval.html', {'reval_form': RevalForm(initial={'reval_date': datetime.date.today()})})

def handle_uploaded_file(f):
    #assume all dates are same
    msg = []
    #iter = 1
    df = pd.read_csv(f)
    if set(df.columns) == {'Instrument', 'Ccy', 'Date', 'Market Rate', 'Curve', 'Term', 'Day Counter'}:
        for idx, row in df.iterrows():
            arg_ = {'name': row['Curve'], 'ref_date': str2date(row['Date']), 'ccy': row['Ccy']}
            arg_upd = {}
            ccy_ = Ccy.objects.get(code=row['Ccy'])
            if ccy_.foreign_exchange_curve == row['Curve']:
                arg_upd['as_fx_curve'] = ccy_
            if ccy_.risk_free_curve == row['Curve']:
                arg_upd['as_rf_curve'] = ccy_
            yts, temp_ = IRTermStructure.objects.update_or_create(**arg_, defaults=arg_upd)
            if row['Term'][:2] == 'ED':
                row['Term'] = row['Term'][:4]
                row['Market Rate'] = 100*float(row['Market Rate'])
            r, temp_ = RateQuote.objects.update_or_create(name=row['Curve']+' '+row['Term'], 
                                                                ref_date=str2date(row['Date']), 
                                                                defaults={ 'tenor': row['Date'], 
                                                                        'instrument': row['Instrument'], 
                                                                        'ccy': Ccy.objects.get(code=row['Ccy']), 
                                                                        'day_counter': row['Day Counter'], 
                                                                        'rate': row['Market Rate']*0.01 }
                                                            )
            yts.rates.add(r)
            msg.append(str(r))
    else:
        msg = 'Fail'
    return msg

@csrf_exempt
def market_data_import(request):
    if request.method == 'POST':
        #form = UploadFileForm(request.POST, request.FILES)
        message = handle_uploaded_file(request.FILES['file'])
        return render(request, 'swpm/market_data_import.html', {'upload_file_form': UploadFileForm(), 'message': message})
    else:
        form = UploadFileForm()
    return render(request, 'swpm/market_data_import.html', {'upload_file_form': form})

@csrf_exempt
def yield_curve(request, curve=None, ref_date=None):
    if request.method == 'POST':
        form = YieldCurveSearchForm(request.POST)
        form_ = dict([ (x[0], x[1]) for x in form.data.dict().items() if len(x[1])>0 ])
        search_result = list(IRTermStructure.objects.filter(**form_).values())
        return render(request, 'swpm/yield_curve.html', {'form': form, 'search_result': search_result})
    elif request.method == 'GET':
        if curve and ref_date:
            yts_model = IRTermStructure.objects.get(name=curve, ref_date=str2date(ref_date))
            yts = yts_model.term_structure()
            dates = yts.dates()
            rates = []
            for i, r in enumerate(yts_model.rates.all()):
                adj_rate = r.rate if r.instrument=='FUT' else r.rate*100
                rates.append({'id': r.id, 'tenor': r.tenor, 'rate': adj_rate, 'date': dates[i+1].ISO(), 
                'zero_rate': yts.zeroRate(dates[i+1], ql.Actual365Fixed(), ql.Continuous).rate()*100
                })
            plt_points = min(len(rates)-1, 14)
            dataPx = px.line(x=[rr['date'] for rr in rates], y=[rr['zero_rate'] for rr in rates], 
                            range_x=[dates[0].ISO(), rates[plt_points]['date']], 
                            range_y=[0, rates[plt_points]['zero_rate']*1.1], 
                            markers=True, labels={'x': 'Date', 'y': 'Zero Rate'})
            app = DjangoDash('yts_plot')
            app.layout = html.Div([dcc.Graph(id="yts_plot_id", figure=dataPx)], 
                    className = "yts_plot_class", 
                    style = { "width" : "100%" }
                )
            data = {'name': yts_model.name, 'ref_date': str2date(ref_date), 'rates': rates}
            return render(request, 'swpm/yield_curve.html', {'form': YieldCurveSearchForm(), 'data': data})
        else:
            return render(request, 'swpm/yield_curve.html', {'form': YieldCurveSearchForm()})
    else:
        return JsonResponse({"error": "GET or PUT request required."}, status=400)