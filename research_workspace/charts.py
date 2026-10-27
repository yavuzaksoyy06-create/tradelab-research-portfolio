"""Plot presentation only: calculations come from research engines."""
import plotly.graph_objects as go
from .adapters import DEMO, ZONES

COLORS={'Beklenen tam mum':'#4bd6b0','Eksik gözlem':'#f7ba65','Tekrarlı gözlem':'#ff7790',
        'Geçersiz / henüz erişilemez':'#ff7790','Kısmi rollover bakımı':'#bca4ff',
        'Rollover bakımı':'#bca4ff','Kısmi özel kesinti':'#bca4ff','Özel kesinti':'#bca4ff',
        'Kısmi seans':'#f7ba65','Hafta sonu / seans kapalı':'#65748b'}

def style(fig,title,height=410):
    fig.update_layout(template='plotly_dark',paper_bgcolor='#0b1322',plot_bgcolor='#0b1322',
        font=dict(family='Segoe UI, sans-serif',color='#dce5f3'),title=dict(text=title,font=dict(size=16)),
        height=height,margin=dict(l=20,r=20,t=85,b=60),showlegend=False,
        hovermode='closest')
    fig.add_annotation(text=DEMO,xref='paper',yref='paper',x=0,y=1.12,showarrow=False,
                       font=dict(color='#f7ba65',size=11),xanchor='left')
    return fig

def forex_chart(view,zone='UTC'):
    frame=view['frame'];fig=go.Figure()
    for status,group in frame.groupby('status',sort=False):
        fig.add_trace(go.Scatter(x=[t.isoformat() for t in group['timestamp']],y=[status]*len(group),mode='markers',name=status,
            marker=dict(color=COLORS.get(status,'#65748b'),size=7,symbol='square'),
            customdata=group[[zone,'UTC','New York','İstanbul']].values,
            hovertemplate='%{customdata[0]}<br>UTC: %{customdata[1]}<br>NY: %{customdata[2]}<br>İstanbul: %{customdata[3]}<extra>%{y}</extra>'))
    # Plotly dates remain absolute UTC; selected local zone is explicitly in hover/table.
    fig.update_xaxes(title='Mum açılışı · UTC (yerel saatler açıklamada ve tabloda)')
    return style(fig,'Seans ve veri bütünlüğü · 15 dakika',450)

def event_chart(view,release):
    fig=go.Figure();frame=view['frame']
    for phase,color in [('Duyuru öncesi','#7caeff'),('Duyuru sonrası','#4bd6b0')]:
        part=frame[frame.phase==phase]
        fig.add_trace(go.Scatter(x=[t.isoformat() for t in part['available_at']],y=part['close'],mode='markers',name=phase,
            marker=dict(color=color,size=10),connectgaps=False,
            customdata=part[['UTC','New York','İstanbul']].values,
            hovertemplate='Sentetik endeks: %{y:.2f}<br>Açılış UTC: %{customdata[0]}<br>NY: %{customdata[1]}<br>İstanbul: %{customdata[2]}<extra></extra>'))
    fig.add_shape(type='line',x0=release,x1=release,y0=0,y1=1,xref='x',yref='paper',line=dict(color='#f7ba65',dash='dash'))
    fig.update_xaxes(title='Gözlemin erişilebilir olduğu an · UTC')
    fig.update_yaxes(title='Varsayımsal fiyat endeksi · başlangıç ≈ 100')
    return style(fig,'Duyuru etrafında gözlenebilir sentetik hareket')
