"""Interior design question bank, from Pratik's Interior_Design.docx (22 September 2026).

Structure: screening questions (availability, stipend, role responsibility) run
first for every interview on this bank; then fundamentals; then scenarios.
The doc's "Assess:" lines are captured as per-question `assess` metadata for the
reporting layer, not as questions. Follow-ups are the doc's actual questions.
"""
from .v2_banks import rows

# A. Initial Screening / Role Fit (from the doc, sections A) — asked of every
# candidate on this bank before fundamentals. Kept verbatim.
DESIGN_SCREENING = rows('design-screen', 'domain', 'screening', [
 ('Are you available to commit to this internship for at least 6 months?',
  ['When would you be available to start?',
   'Do you have any academic or other commitments that could affect your availability?']),
 ('The stipend for this internship is INR 10,000-15,000 per month. Is this stipend range acceptable to you?',
  ['Are you comfortable proceeding with the interview with this stipend structure?',
   'Do you have any concerns regarding the stipend?']),
 ('This role involves redesigning the interior of our office using AutoCAD and other relevant design tools. You would also be responsible for coordinating with interior and other vendors and helping oversee the renovation project from design to execution. Are you comfortable taking responsibility for these aspects of the role?',
  ['Which design tools are you currently comfortable using?',
   'What is your experience with AutoCAD?',
   'Have you worked on any interior design or renovation project before?',
   'Are you comfortable coordinating directly with vendors and contractors?']),
])

DESIGN = (DESIGN_SCREENING
          + rows('design-f', 'domain', 'fundamental', [
    ('What are the key things you would consider when designing or renovating an office space?',
     ['How would office design differ from residential interior design?',
      'What factors would you consider for employee comfort and productivity?',
      'How would you balance aesthetics, functionality, and available space?']),
    ('How would you approach understanding the requirements of an office before creating a design?',
     ['What information would you collect before starting the design?',
      'Who would you need to speak with to understand the requirements?',
      'What would you inspect during an initial site visit?',
      'What measurements or documentation would you collect?',
      'How would you identify which areas of the office need improvement?']),
    ('What factors would you consider when planning the layout of an office?',
     ['How would you decide where to place workstations, meeting areas, storage, and common spaces?',
      'How would you think about movement and circulation?',
      'How would lighting, ventilation, noise, and privacy affect your layout?',
      'How would you approach a situation where the available space is limited?']),
])
          + rows('design-c', 'domain', 'scenario', [
    ('You are asked to help renovate the FlashSpace office, but there is no finalized design or detailed plan yet. What would you do first?',
     ['What would you inspect during your first site visit?',
      'What measurements and information would you collect?',
      'Who would you speak with to understand the requirements?',
      'How would you turn your observations into an initial design proposal?']),
    ('You are asked to find and coordinate with vendors for the turnkey execution of an office renovation project. What steps would you take to identify and select the right vendor?',
     ['Where would you look for potential vendors?',
      'What factors would you compare between different vendors?',
      'How would you evaluate their previous work and experience?',
      'How would you compare quotations?',
      'What would you check before finalizing a vendor?']),
    ('You visit the office and notice that the current layout feels crowded and employees have difficulty moving around. How would you approach improving the space?',
     ['What would you look at before changing the layout?',
      'How would you decide which furniture should be moved or removed?',
      'How would you improve circulation without significantly increasing the renovation cost?',
      'How would you present your proposed layout to the team?']),
    ('The company gives you a limited renovation budget and asks you to make the office look more modern and professional. How would you approach it?',
     ['Which areas would you prioritize?',
      'How would you decide where to spend more and where to save?',
      'Would you consider changing furniture, lighting, wall finishes, branding elements, or decor?']),
    ('You have proposed a new office layout, but the management team disagrees with some of your design choices. How would you handle the feedback?',
     ['How would you understand what they want changed?',
      'How would you explain the reasoning behind your design?',
      'What would you do if their requested change negatively affected the functionality of the space?']),
    ('You are asked to create a mood board or design concept for the office. How would you decide the overall look and feel?',
     ['What would you consider when selecting colors, furniture, materials, lighting, and decor?',
      'How would you make sure the design reflects the company\u2019s brand?',
      'What references or sources would you use for inspiration?']),
    ('During renovation, a contractor tells you that part of your proposed design is not practical to execute within the available budget or space. What would you do?',
     ['What would you ask the contractor before changing the design?',
      'How would you evaluate alternative solutions?',
      'When would you involve your manager or management team?']),
    ('You are responsible for coordinating several parts of the office renovation — furniture, lighting, materials, vendors, and timelines. How would you keep track of everything?',
     ['How would you organize tasks and deadlines?',
      'How would you track vendor requirements and material deliveries?',
      'What would you do if one delayed item affected the rest of the renovation?']),
    ('Imagine you have completed a proposed office design, but before execution you realize that it looks good visually but may not be practical for employees to use every day. What would you do?',
     ['How would you identify potential usability problems?',
      'What would you prioritize between aesthetics and functionality, and why?',
      'How would you test or validate the layout before execution?']),
    ('Imagine you are given the current FlashSpace office and asked to propose how it should be renovated, but you have never worked on an office renovation before. How would you approach the task from day one?',
     ['What would you research first?',
      'What would you measure and document?',
      'How would you create your initial ideas?',
      'Which tools would you use to create the layout or design?']),
]))

DESIGN_ASSESS = {
    'design-screen-1': 'Availability and commitment.',
    'design-screen-2': 'Compensation alignment.',
    'design-screen-3': 'Role understanding, tool proficiency, ownership, practical experience, and willingness to handle project responsibilities.',
    'design-f-1': 'Understanding of commercial office design, functionality, space planning, and workplace requirements.',
    'design-f-2': 'Requirement gathering, site assessment, observation, communication, and planning.',
    'design-f-3': 'Space planning, circulation, functionality, and practical design thinking.',
    'design-c-1': 'Initiative, site assessment, requirement gathering, planning, and ownership.',
    'design-c-2': 'Vendor sourcing, evaluation, negotiation, communication, decision-making, and project coordination.',
    'design-c-3': 'Space optimization, problem-solving, functionality, and communication.',
    'design-c-4': 'Budget awareness, prioritization, creativity, cost-effective design, and decision-making.',
    'design-c-5': 'Communication, handling feedback, design justification, adaptability, and professional judgment.',
    'design-c-6': 'Creativity, visual thinking, research, brand understanding, and presentation skills.',
    'design-c-7': 'Collaboration, execution awareness, problem-solving, adaptability, follow-through, and decision-making.',
    'design-c-8': 'Organization, project coordination, vendor management, prioritization, and communication.',
    'design-c-9': 'Practical design thinking, usability, critical thinking, and willingness to iterate.',
    'design-c-10': 'Learning ability, initiative, research, design process, tool usage, problem-solving, and ownership.',
}
