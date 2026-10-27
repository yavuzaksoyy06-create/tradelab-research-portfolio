"""Event eligibility is not complete response-label observability."""
from .events import _canonical_ts,_parse_ts,is_in_sample,is_predictive_eligible,SAMPLE_CUTOFF_UTC

def response_label_available(event,as_of=SAMPLE_CUTOFF_UTC,*,observations_available_at=()):
    """Temporal gate only; the join layer must separately prove complete bars.

    Delayed observations matter even when the nominal response window has ended.
    No information about response values is read by this function.
    """
    cutoff=_parse_ts(_canonical_ts(as_of,"as_of"))
    if event.research_mode=="predictive":
        eligible=is_predictive_eligible(event,as_of)
        end=event.prediction_horizon_end
    elif event.research_mode=="explanatory_event_study":
        eligible=is_in_sample(event,as_of)
        end=event.response_window_end
    else:return False
    return bool(eligible and end and _parse_ts(end)<=cutoff and
                all(_parse_ts(_canonical_ts(t,"observation.available_at"))<=cutoff for t in observations_available_at))
