"""Transparent local comparisons; no invented global rankings or hardware scores."""

def percentile(score,previous):
    if not previous:return None
    return 100*(sum(v<score for v in previous)+0.5*sum(v==score for v in previous))/len(previous)

