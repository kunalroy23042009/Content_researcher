# Manual Testing Checklist

This checklist is for human verification of the Creator Content Radar app before proceeding to Phase 13 (Deployment).

## Prerequisites
- App running locally: `python -m uvicorn app.main:app --reload`
- Valid YouTube API key, Reddit credentials, and Gemini API key configured in `.env`
- A real YouTube channel URL to test with (preferably one you're familiar with)

---

## Test Cases

### 1. Real Channel URL → Accurate Niche Profile
- [ ] Paste a real YouTube channel URL (e.g., a tech channel, gaming channel, or educational channel)
- [ ] Click "Analyze Channel"
- [ ] Verify the channel title is correct
- [ ] Review the **niche** field - does it accurately describe the channel's focus?
- [ ] Review the **topics** list - are these relevant to the channel's content?
- [ ] Review the **content style** - does this match the channel's actual style?
- [ ] Review the **target audience** - is this a reasonable description?
- [ ] Review the **AI summary** - is it coherent and specific to the channel?

### 2. Competitor List → Relevance Check
- [ ] After analysis completes, verify the competitor section appears
- [ ] Review the list of competitor channels
- [ ] Check if at least 50% of the competitors feel genuinely relevant to the source channel
- [ ] Verify the relevance notes provide useful context
- [ ] Try unchecking some competitors and note the behavior

### 3. Topic Search → Real Results
- [ ] Enter a topic relevant to the channel (e.g., "video editing tips" for a tech channel)
- [ ] Click "Search Content"
- [ ] Verify results are returned (not empty)
- [ ] Check that results include both YouTube and Reddit content
- [ ] Verify each result has a working URL (click a few to test)
- [ ] Check that engagement scores are reasonable numbers

### 4. Classification Labels → Spot Check
- [ ] Review the results grouped into Trending, Popular, and Underrated
- [ ] Spot-check 5 results across different classifications
- [ ] For each result, compare the classification label with the raw metrics:
  - **Trending**: Should have high recent engagement relative to age
  - **Popular**: Should have high absolute view counts/engagement
  - **Underrated**: Should have good quality but lower engagement than expected
- [ ] Do the labels make sense given the metrics shown?

### 5. AI Insight → Quality Check
- [ ] Review the **AI Insight** section at the top of search results
- [ ] Is the **summary** specific to the topic and channel, or generic filler?
- [ ] Are the **content angles** actionable and creative ideas?
- [ ] If a **content gap** is identified, is it a genuine opportunity?
- [ ] Overall, would this insight actually help a creator plan content?

### 6. Cache Hit → Repeat Search
- [ ] Perform a topic search for a specific query
- [ ] Note the time
- [ ] Perform the **exact same** topic search again immediately
- [ ] Check the server logs (terminal where uvicorn is running)
- [ ] Look for cache-related log messages or faster response time
- [ ] Verify the results are identical to the first search
- [ ] (Optional) Wait 24+ hours and repeat to verify cache expiration

---

## Additional Edge Cases to Try

### Invalid Inputs
- [ ] Paste a garbage URL (e.g., "not-a-url") → should show clear error
- [ ] Paste a non-YouTube URL → should show clear error
- [ ] Leave channel URL blank → should show validation error
- [ ] Leave topic blank → should show validation error

### UI/UX Checks
- [ ] Loading indicators appear during API calls
- [ ] Error messages are clear and helpful
- [ ] Page layout is readable on different screen sizes
- [ ] No console errors in browser DevTools during normal use

---

## Notes

Use this section to record any issues found during testing:

- **Issue 1**: 
- **Issue 2**: 
- **Issue 3**: 

---

## Sign-off

**Tester**: ___________________
**Date**: ___________________
**Result**: [ ] Pass / [ ] Fail (with notes above)
