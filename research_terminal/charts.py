"""Ordinal completed-bar chart. All overlays use the same causal coordinates."""
import html
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

MARKERS={"signal":("Signal","triangle-up-open","#56b4e9"),
 "accepted_entry":("Simulated long entry","triangle-up","#009e73"),
 "rejected_entry":("Rejected opportunity","x-open","#d89038"),
 "exit":("Simulated timed exit","triangle-down","#cc79a7"),
 "stop_exit":("Stop-loss exit","x","#ef6675"),
 "target_exit":("Target exit","star","#66d9aa"),
 "risk_lock":("Risk lock","hexagram","#f0e442")}

def style(fig,height=720):
 fig.update_layout(template="plotly_dark",height=height,paper_bgcolor="#0c1422",plot_bgcolor="#0c1422",
  font={"family":"Segoe UI","color":"#cbd5e1","size":12},margin={"l":35,"r":55,"t":65,"b":40},
  legend={"orientation":"h","y":1.15,"font":{"size":10}},hovermode="closest")
 return fig

def clock_label(stamp):
 return pd.Timestamp(stamp).tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M %Z")

def market(state,history=100,events=None,selected=None,visibility=None,selected_trade=None):
 visible={k:True for k in ("zones","pivots","execution","rejected","signals","atr","volume")}
 visible.update(visibility or {})
 bars=state["bars"].tail(history)
 fig=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=.045,row_heights=[.65,.20,.15])
 if bars.empty:
  fig.add_annotation(text="No completed candles available. Advance replay.",showarrow=False)
  return style(fig)
 xs=[int(i) for i in bars.index];left,right=xs[0],xs[-1]
 stamps={i:str(bars.loc[i,"bar_end"]) for i in xs}
 custom=[[stamps[i],clock_label(stamps[i])] for i in xs]
 fig.add_trace(go.Candlestick(x=xs,open=bars.open,high=bars.high,low=bars.low,close=bars.close,
  customdata=custom,text=[f'{clock_label(stamps[i])}<br>UTC close {stamps[i]}<br>O {bars.loc[i,"open"]:.4f} · H {bars.loc[i,"high"]:.4f}<br>L {bars.loc[i,"low"]:.4f} · C {bars.loc[i,"close"]:.4f}<br>Volume {bars.loc[i,"volume"]:,.0f}' for i in xs],hoverinfo="text",
  name=state["symbol"],increasing_line_color="#35d4ab",decreasing_line_color="#fc7385",meta={"role":"candles"}),row=1,col=1)
 if visible["volume"]:
  fig.add_trace(go.Bar(x=xs,y=bars.volume,name="Volume",opacity=.6,
   marker_color=["#35d4ab" if c>=o else "#fc7385" for c,o in zip(bars.close,bars.open)],
   customdata=custom,hovertemplate="%{customdata[1]}<br>Volume %{y:,.0f}<extra></extra>",meta={"role":"volume"}),row=2,col=1)
 snaps=state["snapshots"]
 if visible["atr"]:
  ax=[];ay=[];ac=[];previous=None
  for i in xs:
   session=bars.loc[i,"session"]
   if previous is not None and previous!=session:ax.append(None);ay.append(None);ac.append([None,None])
   ax.append(i);ay.append(snaps[i]["atr"]);ac.append([stamps[i],clock_label(stamps[i])]);previous=session
  fig.add_trace(go.Scatter(x=ax,y=ay,customdata=ac,connectgaps=False,name="Causal ATR",
   line={"color":"#b899ff","width":1.5},meta={"role":"atr"},
   hovertemplate="%{customdata[1]}<br>ATR %{y:.4f}<extra></extra>"),row=3,col=1)
 if visible["zones"]:
  active={z["id"] for z in state["snapshot"]["zones"]};segments={}
  for i in xs[:-1]:
   for z in snaps[i]["zones"]:
    key=(z["id"],z["lower"],z["upper"],z["kind"]);spans=segments.setdefault(key,[])
    if spans and spans[-1][1]==i and bars.loc[i,"session"]==bars.loc[i-1,"session"]:spans[-1][1]=i+1
    else:spans.append([i,i+1])
  for (zone,lower,upper,kind),spans in segments.items():
   color="rgba(53,212,171,.09)" if kind=="support" else "rgba(252,115,133,.09)"
   if zone not in active:color="rgba(148,163,184,.035)"
   for start,end in spans:fig.add_shape(type="rect",xref="x",yref="y",x0=start,x1=end,y0=lower,y1=upper,
    line_width=0,fillcolor=color,layer="below",name=zone)
  for z in state["snapshot"]["zones"]:
   fig.add_trace(go.Scatter(x=[right],y=[(z["lower"]+z["upper"])/2],mode="markers",showlegend=False,
    marker={"symbol":"line-ew","size":10,"color":"#35d4ab" if z["kind"]=="support" else "#fc7385"},
    text=[f'{z["id"]} {z["kind"]}<br>{z["lower"]:.4f}–{z["upper"]:.4f}<br>As of {clock_label(stamps[right])}'],
    meta={"role":"zone","zone_id":z["id"]},hovertemplate="%{text}<extra></extra>"),row=1,col=1)
   if bars.low.min()<=z["upper"] and z["lower"]<=bars.high.max():
    fig.add_annotation(x=right,y=(z["lower"]+z["upper"])/2,text=z["id"],showarrow=False,xanchor="left",font={"size":9})
 pivots=[p for p in state["pivots"] if left<=p["confirmed_index"]<=right]
 if visible["pivots"] and pivots:
  fig.add_trace(go.Scatter(x=[p["confirmed_index"] for p in pivots],y=[p["price"] for p in pivots],
   mode="markers",name="Confirmed pivot",marker={"symbol":"diamond-open","size":6,"color":"#aab8ce"},
   text=[f'{p["kind"]}<br>Pivot: {clock_label(p["pivot_at"])}<br>Confirmed: {clock_label(p["confirmed_at"])}' for p in pivots],
   meta={"role":"pivot"},hovertemplate="%{text}<br>%{y:.4f}<extra></extra>"),row=1,col=1)
 for kind,(name,symbol,color) in MARKERS.items():
  if kind=="signal" and not visible["signals"]:continue
  if kind=="rejected_entry" and not visible["rejected"]:continue
  if kind in ("accepted_entry","exit","stop_exit","target_exit") and not visible["execution"]:continue
  group=[e for e in events or [] if e["marker_type"]==kind and left<=e["known_index"]<=right and e["price"] is not None]
  if not group:continue
  texts=[]
  for e in group:
   p=e["payload"];ev=p.get("evidence") or {}
   fields={"Event ID":e["event_id"],"Symbol":e["symbol"],"Type":name,"Actual time":e["timestamp"],
    "Observable after":e["observable_at"],"Strategy":p.get("strategy"),"Zone":p.get("zone_id",ev.get("zone_id")),
    "Decision":p.get("status"),"Saved reason":p.get("reason") or p.get("binding_constraint") or p.get("detail")}
   texts.append("<br>".join(f"{k}: {html.escape(str(v)) if v is not None else 'Not recorded / Unavailable'}" for k,v in fields.items()))
  fig.add_trace(go.Scatter(x=[e["known_index"] for e in group],y=[e["price"] for e in group],
   customdata=[e["event_id"] for e in group],text=texts,mode="markers",name=name,
   marker={"symbol":symbol,"color":color,"size":[17 if e["event_id"]==selected else 10 for e in group],"line":{"width":1}},
   meta={"role":"event","kind":kind},hovertemplate="%{text}<br>Price %{y:.4f}<extra></extra>"),row=1,col=1)
 if selected_trade and visible["execution"]:
  start=max(left,int(selected_trade["entry_index"]));end=min(right,int(selected_trade.get("exit_index",right)))
  if start<=end:
   for field,color in (("stop","#ef6675"),("target","#66d9aa")):
    if selected_trade.get(field) is not None:fig.add_shape(type="line",x0=start,x1=end,y0=selected_trade[field],y1=selected_trade[field],
     line={"color":color,"dash":"dot","width":1},name="planned_"+field)
 fig.add_vline(x=right,line_width=1,line_dash="dash",line_color="#74849a",row=1,col=1)
 ticks=[i for j,i in enumerate(xs) if j==0 or bars.loc[i,"session"]!=bars.loc[xs[j-1],"session"]]
 if len(ticks)>8:ticks=ticks[::max(1,len(ticks)//6)]
 if len(ticks)<3:ticks=xs[::max(1,len(xs)//5)]
 fig.update_xaxes(type="linear",range=[left-.8,right+1],tickmode="array",tickvals=ticks,
  ticktext=[pd.Timestamp(stamps[i]).tz_convert("America/New_York").strftime("%b %d<br>%H:%M %Z") for i in ticks],
  rangeslider_visible=False,showgrid=False)
 low=float(bars.low.min());high=float(bars.high.max());pad=max((high-low)*.12,float(state["snapshot"].get("atr") or .01))
 fig.update_yaxes(range=[low-pad,high+pad],row=1,col=1);fig.update_yaxes(gridcolor="#1b293c")
 fig.update_xaxes(title_text="Completed trading bars · America/New_York",row=3,col=1)
 fig.update_layout(uirevision=f'{state["symbol"]}-{state["session"]}-{history}',meta={"bar_times":stamps,"axis":"ordinal_completed_bar"})
 return style(fig)

def portfolio(equity):
 fig=make_subplots(rows=4,cols=1,shared_xaxes=True,vertical_spacing=.07)
 for field,row in [("equity",1),("cash",2),("exposure_fraction",3),("max_drawdown",4)]:
  fig.add_trace(go.Scatter(x=equity.timestamp,y=equity[field],name=field,mode="lines"),row=row,col=1)
 for name,row in [("Equity USD",1),("Cash USD",2),("Exposure fraction",3),("Drawdown fraction",4)]:fig.update_yaxes(title_text=name,row=row,col=1)
 return style(fig,760)

