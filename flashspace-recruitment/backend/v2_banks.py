"""Curated from the two user-supplied DOCX banks, 10 September 2026.

Six actual generic sections take precedence over the source's stale Q7 references.
Truncated source follow-up excluded. Routine wording narrowed to responsibilities
rather than private lifestyle. Domain questions retain source wording.
"""
BANK_VERSION = 'flashspace-banks-2026-09-10-v1'


def rows(prefix, stage, category, pairs):
    return [{'id': f'{prefix}-{i+1}', 'stage': stage, 'category': category,
             'text': q, 'followups': fs} for i, (q, fs) in enumerate(pairs)]


GENERIC = rows('generic', 'generic', 'generic', [
 ('Could you tell us about your educational journey, including your schooling, academics, activities, projects, achievements, and other experiences that you have been involved in?', ['What was your role in that project?', 'Could you give us one specific example?']),
 ('Where do you see yourself in the next 3 years? What are your longer-term goals for 5 to 10 years, and do you have any plans for further studies? What are you doing today to move toward those goals?', ['What steps are you currently taking toward that goal?', 'What is one skill or area you would like to significantly improve over the next year?']),
 ('Tell us about something you worked on consistently for a long period of time. How much time did you dedicate to it, and what kept you going? What was the most difficult period during that experience, and how did you handle it?', ['What did you do when you got stuck?', 'What was the final outcome?']),
 ('How do you plan the responsibilities you need to accomplish during a typical day? When you have multiple responsibilities or deadlines, how do you prioritize them?', ['Can you give us an example of a time when you had several things to do at once? How did you manage them?', 'How do you manage important responsibilities when your schedule changes?']),
 ('Have you ever started your own venture, startup, business, project, initiative, or any activity where you were responsible for taking it from an idea to execution?', ['What exactly was your responsibility?', "Have you ever taken ownership of something that wasn't formally assigned to you?"]),
 ('Why are you interested in this particular role, and why did you choose to apply to Flashspace?', ['What specifically are you hoping to learn here?', 'How does this role fit into your longer-term plans?']),
])

SALES = rows('sales-f', 'domain', 'fundamental', [
 ('What is prospecting in sales, and why is it important?', ['What are some ways a salesperson can find potential customers?', 'What is the difference between inbound and outbound leads?']),
 ('What is lead qualification, and why is it important?', ['What information would you want to know about a lead?', 'What makes a lead qualified or unqualified?']),
 ('What is a CRM, and why do sales teams use it?', ['What information should a salesperson record after speaking with a prospect?', 'What problems can occur if CRM records are not maintained properly?']),
]) + rows('sales-c', 'domain', 'scenario', [
 ('You receive a new inbound lead who has shown interest in Flashspace. Walk me through what you would do from the moment you receive the lead until you either convert the lead or decide that it is not qualified.', ['What would you want to understand during the first conversation?', 'How would you decide the next step?']),
 ('You have 50 leads, but you only have enough time today to contact 15. How would you decide which 15 to contact first?', ['What information would you use to prioritize them?', 'How would you know whether your prioritization strategy is working?']),
 ('A prospect tells you, "Your price is too high. I can get something similar from another company for less." How would you respond?', ['What would you ask before responding?', 'Would you immediately offer a discount? Why or why not?']),
 ('You had a good conversation with a prospect who said they were interested, but they have not responded to your follow-ups for a week. What would you do?', ['How would you structure your next follow-up?', 'Would you change the message or channel? Why?']),
 ('Your sales conversion rate has dropped significantly this month. How would you investigate the problem?', ['Which part of the sales funnel would you examine first?', 'What data would you look at?']),
])
OPERATIONS = rows('operations-f', 'domain', 'fundamental', [
 ('What do you understand by operations in a company?', ['What kinds of activities are generally handled by an operations team?', 'Why is coordination important in operations?']),
 ('What is a bottleneck in an operational process, and how can it affect a workflow?', ['How would you identify a bottleneck?', 'What could you do after identifying one?']),
 ('What is process documentation, and why is it important?', ['What information would you include in a process document?', 'How can documentation help when another person needs to take over a task?']),
]) + rows('operations-c', 'domain', 'scenario', [
 ('You have five tasks with different deadlines, and two different teams are waiting for your work. How would you organize and prioritize your day?', ['What factors would you consider when prioritizing?', 'How would you communicate a possible delay?']),
 ('A process that normally takes one day is suddenly taking three days. How would you identify what is causing the delay?', ['Where would you start investigating?', 'How would you determine whether it is a one-time issue or recurring?']),
 ('You need information from three teams to complete an important task, but one team is not responding. How would you handle the situation?', ['How would you follow up?', 'When would you escalate the issue?']),
 ('You discover that you entered incorrect information into an important company record, and another team may already have used that information. What would you do?', ['Who would you inform?', 'What would you change to prevent it from happening again?']),
 ('You notice that the same operational problem keeps occurring every week. How would you approach it?', ['How would you collect evidence?', 'How would you measure whether your solution worked?']),
])
MARKETING = rows('marketing-f', 'domain', 'fundamental', [
 ('What is the difference between organic marketing and paid marketing?', ['Can you give examples of each?', 'What are the advantages and limitations of each approach?']),
 ('What is a target audience, and why is identifying it important before creating a marketing campaign?', ['What information would you use to understand a target audience?', 'How would you identify their problems or pain points?']),
 ('What are some important marketing metrics, and what do metrics such as reach, impressions, engagement, clicks, CTR, leads, and conversion rate tell you?', ['How is CTR calculated?', 'Why is it dangerous to judge a campaign using only one metric?']),
]) + rows('marketing-c', 'domain', 'scenario', [
 ('You are asked to increase awareness and generate leads for Flashspace over the next 30 days. How would you build your initial marketing plan?', ['Who would you target?', 'Which channels would you prioritize and why?']),
 ('You launch a campaign that receives many clicks but generates very few leads. How would you investigate the problem?', ['Which metrics would you examine?', 'What experiment would you run next?']),
 ('You are responsible for Flashspace’s social media and organic content for a month. How would you decide what content to create and publish?', ['How would you research content ideas?', 'What would you do if engagement remained low?']),
 ('You have a limited advertising budget and need to generate leads. How would you approach setting up and testing the campaign?', ['What would you test first?', 'When would you increase, decrease, or stop spending?']),
 ('You need to produce a month’s worth of marketing content with a small team. How would you use AI tools to make the process faster while maintaining accuracy, quality, and brand consistency?', ['Which parts would you keep under human review?', 'How would you check AI-generated information?']),
 ('You are given complete responsibility for Flashspace’s marketing for the next 30 days, but nobody gives you a detailed plan. What would you do?', ['What would you do during your first week?', 'What would you present to management at the end of 30 days?']),
])
BANKS = {'sales': SALES, 'operations': OPERATIONS, 'marketing': MARKETING}
# Explicit identity mappings, not title inference. Recruiters must map new roles.
DEFAULT_MAPPINGS = {'generalist-sales': 'sales', 'generalist-operations': 'operations', 'ai-marketing': 'marketing'}
