"""Create repeatable local-only sample communities and conversations."""

import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Account, AccountType
from communities.models import (
    Channel,
    Community,
    DirectConversation,
    DirectMessage,
    GuestMembership,
    Membership,
    Message,
    Reaction,
)

PEOPLE = {
    "maya":   "Maya Chen",
    "jordan": "Jordan Rivera",
    "sam":    "Sam Okonkwo",
    "alex":   "Alex Park",
    "priya":  "Priya Nair",
    "wei":    "Wei Zhang",
    "nina":   "Nina Kowalski",
    "oliver": "Oliver Reyes",
    "zara":   "Zara Ahmed",
}

GROUPS = [
    {
        "name": "NYU Calculus Study Circle",
        "description": "Problem sets, office hours, and exam prep for Calculus I.",
        "school": "New York University",
        "course": "MATH-UA 121",
        "owner": "maya",
        "members": ["jordan", "sam", "alex", "priya"],
        "channels": {
            "general": [
                ("maya",   "Hey everyone! Welcome to the NYU Calculus study circle 🎉"),
                ("jordan", "Thanks for setting this up Maya! Really needed a study group for this class."),
                ("sam",    "Same, Calc has been rougher than I expected."),
                ("alex",   "The problem sets are no joke. Anyone else struggling with section 4.3?"),
                ("priya",  "Yes! The related rates problems are killing me."),
                ("maya",   "Ok let's schedule a session this week. Thursday 6pm work for everyone?"),
                ("jordan", "Thursday works for me!"),
                ("sam",    "I can do Thursday. Library study room?"),
                ("alex",   "Thursday works. Bobst 4th floor has big tables."),
                ("priya",  "Perfect, I'll book a room. See everyone Thursday!"),
                ("maya",   "Also Prof. Kim's office hours are Tuesday 2-4pm if anyone wants to go together."),
                ("jordan", "Good to know. Anyone gone to office hours yet?"),
                ("sam",    "I went last week. She's really helpful, explains things differently than in lecture."),
            ],
            "problem-sets": [
                ("priya",  "Starting on PS5 now. Anyone want to work through it together?"),
                ("alex",   "Yes! Problem 3 is integration by parts right?"),
                ("priya",  "Yeah, the LIATE rule applies. Try u = ln(x) first."),
                ("maya",   "For integration by parts remember: ∫u dv = uv − ∫v du. LIATE helps pick u: Logs, Inverse trig, Algebraic, Trig, Exponential."),
                ("jordan", "Oh that's a great mnemonic. So for ∫x·e^x dx we pick u=x?"),
                ("maya",   "Exactly! u=x (algebraic), dv=e^x dx. Then du=dx, v=e^x."),
                ("sam",    "I got stuck on problem 7 — implicit differentiation with a trig function."),
                ("priya",  "Differentiate both sides with respect to x, don't forget the chain rule on y terms."),
                ("alex",   "For sin(xy) = x, you get cos(xy)·(y + x·y') = 1, then solve for y'."),
                ("sam",    "Oh I see it now. Thanks!"),
                ("jordan", "PS5 problem 12 is a related rates one. A ladder sliding down a wall."),
                ("maya",   "Classic! Draw a diagram first, label everything. x² + y² = L² where L is constant."),
                ("priya",  "Differentiate implicitly with respect to t: 2x(dx/dt) + 2y(dy/dt) = 0."),
                ("jordan", "Got it! Plug in the given values for x, y, and dx/dt to find dy/dt."),
            ],
            "exam-prep": [
                ("maya",   "Midterm is in 3 weeks! Let's make a study plan."),
                ("jordan", "I made a review outline — covers limits, derivatives, and integration basics."),
                ("sam",    "Can you share it in resources? That would be super helpful."),
                ("jordan", "Posted! It's based on the syllabus topics."),
                ("alex",   "The chain rule section was confusing for me in lecture. Anyone have good notes?"),
                ("priya",  "Chain rule: d/dx[f(g(x))] = f'(g(x))·g'(x). Think 'outside times inside prime'."),
                ("alex",   "That phrasing helps actually. Outside times inside prime."),
                ("maya",   "For the exam, implicit differentiation shows up a lot. Practice those!"),
                ("sam",    "Also related rates. Prof. Kim said there will definitely be one on the midterm."),
                ("jordan", "I'll do all the practice problems from chapter 3 this weekend."),
                ("priya",  "Let's do a mock exam session next Tuesday? I'll bring the old midterms."),
                ("maya",   "Yes! Tuesday 5pm? Same room as Thursday."),
                ("alex",   "I'll be there. Also don't forget to review L'Hôpital's rule."),
            ],
            "resources": [
                ("jordan", "Here's my chapter 3-5 review outline: integration rules, derivative rules, and trig identities."),
                ("priya",  "Paul's Online Math Notes is great for Calc I: tutorial.math.lamar.edu"),
                ("sam",    "Professor Leonard on YouTube is amazing for calculus explanations."),
                ("alex",   "Khan Academy has good practice problems too, especially for related rates."),
                ("maya",   "MIT OpenCourseWare has old exams: ocw.mit.edu — search 18.01"),
                ("jordan", "Also the Wolfram Alpha step-by-step solver is useful for checking your work."),
                ("priya",  "Photomath app works for checking derivatives if you're on your phone."),
                ("sam",    "I found a really good LIATE rule cheat sheet, posting it as an image."),
                ("maya",   "Don't forget: office hours notes from last week covered exactly what's on the exam."),
            ],
        },
        "reactions": {
            "general":      [("maya",   "🎉"), ("priya",  "👍")],
            "problem-sets": [("alex",   "👍"), ("sam",    "🔥")],
            "exam-prep":    [("jordan", "🎉"), ("alex",   "👍")],
            "resources":    [("maya",   "👍"), ("priya",  "🔥")],
        },
        "pins": {
            "general":      0,
            "problem-sets": 3,
            "exam-prep":    6,
            "resources":    0,
        },
    },
    {
        "name": "Brooklyn Coding Collective",
        "description": "Collaborative coding for CISC 3115 — algorithms, web dev, and project help.",
        "school": "CUNY Brooklyn College",
        "course": "CISC 3115",
        "owner": "alex",
        "members": ["priya", "sam", "wei"],
        "channels": {
            "general": [
                ("alex",  "Welcome to the Brooklyn Coding Collective! 💻"),
                ("priya", "Finally a study group for this class. The BST assignment has me stumped."),
                ("sam",   "Same. I've been staring at the insert method for like two hours."),
                ("wei",   "The recursive approach is cleaner imo. Want me to walk through it?"),
                ("alex",  "Yes please! I'm getting confused with the base cases."),
                ("wei",   "Base case: if root is null, return new node. Otherwise compare key and recurse left or right."),
                ("priya", "Oh that makes sense. The recursion bottoms out at a null leaf."),
                ("sam",   "When's the BST assignment due?"),
                ("alex",  "Next Friday. We should pair program over video call this weekend."),
                ("priya", "Saturday afternoon works for me."),
                ("wei",   "Saturday 2pm? I can share my screen."),
                ("sam",   "I'll be there. We can use the Discord— I mean, this platform 😄"),
                ("alex",  "Haha yes. See everyone Saturday!"),
            ],
            "algorithms": [
                ("wei",   "Starting a thread on BST implementation. Key operations: insert, search, delete."),
                ("alex",  "Delete is the tricky one. Three cases: leaf, one child, two children."),
                ("wei",   "Exactly. For two-children case, find the inorder successor (smallest in right subtree)."),
                ("priya", "I keep forgetting to handle the two-child case in delete. Got a null pointer last night."),
                ("sam",   "For inorder successor: go right once, then keep going left until null."),
                ("alex",  "Also worth implementing a height() method and checking if the tree is balanced."),
                ("wei",   "AVL trees handle balancing automatically with rotations. Out of scope for the assignment but good to know."),
                ("priya", "What's the time complexity for BST operations?"),
                ("alex",  "Average case: O(log n). Worst case (degenerate/skewed tree): O(n)."),
                ("sam",   "That's why balanced trees matter — AVL, Red-Black, etc."),
                ("wei",   "For the homework though, a plain BST is fine. Focus on correctness first."),
                ("priya", "Good advice. I'll get it working then optimize."),
                ("alex",  "Also remember to handle duplicates — either reject or allow in right subtree."),
            ],
            "web-dev": [
                ("priya", "Side project question: should I use React or SvelteKit for my portfolio?"),
                ("alex",  "SvelteKit all the way. Less boilerplate, faster, and the DX is amazing."),
                ("sam",   "I switched from React to Svelte last year and don't miss it."),
                ("wei",   "Svelte's reactivity model is simpler — no useState hooks, just $state()."),
                ("priya", "Does SvelteKit do SSR out of the box?"),
                ("alex",  "Yes! File-based routing, SSR, and static generation all built in."),
                ("sam",   "The learning curve is gentler than Next.js too."),
                ("wei",   "For a portfolio site I'd probably go static with `svelte-kit build` and deploy to Vercel."),
                ("priya", "Ok sold. SvelteKit it is. Any good tutorials?"),
                ("alex",  "Official Svelte tutorial at learn.svelte.dev is excellent. Do the whole thing."),
                ("sam",   "Also Joy of Code on YouTube has great Svelte content."),
                ("wei",   "For styling, I like Tailwind with Svelte — works really well together."),
                ("priya", "Thanks team! Starting this weekend after we finish the BST assignment."),
            ],
            "help": [
                ("sam",   "Debugging session: my BST search returns null for elements I know are in the tree."),
                ("wei",   "Can you share your search code?"),
                ("sam",   "function search(root, key) { if (!root) return null; if (key === root.val) return root; return search(root.left, key); }"),
                ("alex",  "Found it! You're only recursing left. You need to check right too."),
                ("sam",   "Oh no. Such a silly bug 😅"),
                ("wei",   "Classic! Add: if (key < root.val) return search(root.left, key); else return search(root.right, key);"),
                ("sam",   "Fixed! Tests pass now. Thank you!"),
                ("priya", "I also had a question — how do I print the BST in inorder (sorted) sequence?"),
                ("alex",  "Inorder traversal: left subtree, root, right subtree. Recursively."),
                ("wei",   "function inorder(root) { if (!root) return; inorder(root.left); print(root.val); inorder(root.right); }"),
                ("priya", "Perfect, that gives sorted output since BST property is maintained."),
                ("sam",   "Can confirm, this is the right approach. Tested it on mine."),
            ],
        },
        "reactions": {
            "general":    [("wei",   "🎉"), ("sam",   "👍")],
            "algorithms": [("priya", "🔥"), ("alex",  "👍")],
            "web-dev":    [("sam",   "🎉"), ("wei",   "👍")],
            "help":       [("priya", "😂"), ("alex",  "🎉")],
        },
        "pins": {
            "general":    0,
            "algorithms": 1,
            "web-dev":    0,
            "help":       5,
        },
    },
    {
        "name": "MCAT Prep NYC",
        "description": "Structured MCAT prep group — full length practice, Anki, and content review.",
        "school": "New York University",
        "course": "MCAT Preparation",
        "owner": "wei",
        "members": ["nina", "priya", "jordan"],
        "channels": {
            "general": [
                ("wei",   "Welcome to MCAT Prep NYC! Testing date accountability starts here."),
                ("nina",  "I'm targeting the April exam. Anyone else?"),
                ("priya", "April too! When did you start prepping?"),
                ("nina",  "About 3 months ago. Just got my FL1 score back — 506."),
                ("wei",   "506 is a solid start. What sections need work?"),
                ("nina",  "CARS is my weak spot. I keep running out of time."),
                ("jordan","Same. CARS is brutal. I've been reading The Economist every day to practice."),
                ("priya", "The Economist tip is everywhere — does it actually help?"),
                ("jordan","Yes! Dense academic prose with arguments you have to follow. Really trains active reading."),
                ("wei",   "Also practice passage-mapping. Don't try to memorize, understand the argument structure."),
                ("nina",  "I'll try daily Economist passages starting this week."),
                ("priya", "What full-length practice tests are you all using? AAMC only or third party too?"),
                ("wei",   "AAMC FLs are the gold standard. Save them for later prep. Use Blueprint or Kaplan FLs earlier."),
                ("jordan","Agreed. I wasted an AAMC FL early on — keep them for the last 6 weeks."),
                ("nina",  "Good tip. I have 4 Blueprint FLs left. That should cover early review."),
            ],
            "bio-biochem": [
                ("priya", "Content review thread: amino acids. Who can name all 20?"),
                ("wei",   "Mnemonic I use: 'Gly Ala Val Leu Ile Pro Phe Trp Met Ser Thr Cys Tyr Asn Gln Asp Glu Lys Arg His'"),
                ("nina",  "Do we need to know pKa values for all of them?"),
                ("wei",   "Know the charged ones at physiological pH (7.4): Asp (-), Glu (-), Lys (+), Arg (+), His (~neutral)."),
                ("jordan","Enzyme kinetics is another big area. Michaelis-Menten?"),
                ("priya", "Km = substrate concentration at half Vmax. Low Km = high enzyme affinity."),
                ("wei",   "Competitive inhibitors increase apparent Km, don't change Vmax."),
                ("nina",  "Noncompetitive inhibitors decrease Vmax, don't change Km."),
                ("jordan","And uncompetitive inhibitors decrease both Km and Vmax."),
                ("priya", "I always mix up competitive and noncompetitive on practice questions."),
                ("wei",   "Trick: competitive inhibitor competes with substrate — can be overcome with excess substrate, so Vmax unchanged."),
                ("nina",  "That makes sense. Substrate wins out if there's enough of it."),
                ("jordan","Also study cell signaling — GPCR, receptor tyrosine kinases, second messengers."),
                ("priya", "cAMP, PKA, IP3/DAG, MAPK cascade. Got it. Anki has good decks for all of this."),
            ],
            "cars-verbal": [
                ("jordan","Daily CARS practice thread. Post your score and one thing you learned."),
                ("nina",  "Did 3 passages today, 9/12 correct. Missed 2 on philosophy passage — inference questions."),
                ("priya", "Inference questions are hard. You have to stay close to the text."),
                ("jordan","Rule for CARS: the answer is always supported by something in the passage. Don't bring outside knowledge."),
                ("wei",   "That's the key insight. MCAT CARS tests reading comprehension, not your knowledge of the topic."),
                ("nina",  "I keep getting drawn to answers that sound 'right' medically but aren't in the passage."),
                ("jordan","Exactly the trap. The right answer might sound weird but is directly supported."),
                ("priya", "Strategy: read the question stem first, then the passage, then eliminate answers not directly supported."),
                ("wei",   "Also: look for the author's main argument and tone. Most questions relate to it."),
                ("nina",  "The Economist reading is helping. Today's article was about central bank policy and I read every word."),
                ("jordan","Great! Try timing yourself — 10 minutes per passage including questions is the target."),
                ("priya", "I'm at 12-13 min per passage. Need to speed up."),
                ("wei",   "Don't sacrifice accuracy for speed yet. Speed comes with practice. Focus on process first."),
            ],
            "study-schedule": [
                ("wei",   "Let's sync study schedules. What's everyone's daily hour commitment?"),
                ("nina",  "I'm doing 3 hours on weekdays, 6 on weekends."),
                ("priya", "Similar — 2-3 hrs/day. More on weekends."),
                ("jordan","I'm doing 4 hrs/day total: 2 content review, 1 practice questions, 1 review."),
                ("wei",   "Good structure. Question-first then review is more efficient than passive reading."),
                ("nina",  "I've been doing passive reading which probably explains my plateau."),
                ("priya", "Active recall is key — Anki is perfect for this. I do 200-300 new cards/day."),
                ("jordan","I use the AnKing deck for MCAT. Massive but very comprehensive."),
                ("wei",   "AnKing is great. Filter by tag for the section you're reviewing."),
                ("nina",  "I'll set up Anki this week. How many reviews per day do you all manage?"),
                ("jordan","I do new + reviews in one session. About 45 min total."),
                ("priya", "Full length tests every 2 weeks, content review in between."),
                ("wei",   "Let's do a group FL debrief after each test? We can share what we got wrong."),
                ("nina",  "Yes! Accountability and shared learning. I'm in."),
            ],
        },
        "reactions": {
            "general":        [("priya", "👍"), ("jordan", "🎉")],
            "bio-biochem":    [("nina",  "🔥"), ("wei",    "👍")],
            "cars-verbal":    [("jordan","👍"), ("nina",   "🎉")],
            "study-schedule": [("priya", "🔥"), ("wei",    "👍")],
        },
        "pins": {
            "general":        0,
            "bio-biochem":    1,
            "cars-verbal":    2,
            "study-schedule": 4,
        },
    },
    {
        "name": "Columbia Macro Study Group",
        "description": "Macroeconomics deep dive — IS-LM models, current events, and problem set help.",
        "school": "Columbia University in the City of New York",
        "course": "ECON 3213",
        "owner": "nina",
        "members": ["oliver", "maya", "sam"],
        "channels": {
            "general": [
                ("nina",   "Welcome everyone! Intermediate Macro is finally getting interesting."),
                ("oliver", "The IS-LM model threw me off at first but it's starting to click."),
                ("maya",   "Same. Once you understand what shifts each curve it makes more sense."),
                ("sam",    "The problem sets are intense. PS3 question 2 took me an hour."),
                ("nina",   "Which question was that?"),
                ("sam",    "The one where fiscal policy is used in a liquidity trap. Spoiler: IS shifts right but LM is flat."),
                ("oliver", "So output increases but interest rates don't rise. Fiscal policy is effective in a trap."),
                ("maya",   "Right! That's actually the Keynesian argument for stimulus during recessions."),
                ("nina",   "The 2008 crisis is a good real-world case. Fed hit zero lower bound, IS shifted left."),
                ("oliver", "And the stimulus packages were trying to shift IS back right."),
                ("sam",    "Study session this week? I need help with the exchange rate extensions."),
                ("maya",   "Thursday works. We can tackle the Mundell-Fleming model too."),
                ("nina",   "Perfect. I'll grab a Uris library room."),
            ],
            "is-lm-models": [
                ("oliver", "IS-LM review: IS curve = goods market equilibrium. LM = money market equilibrium."),
                ("maya",   "IS curve slopes downward: higher r → lower investment → lower output."),
                ("nina",   "LM curve slopes upward: higher Y → higher money demand → higher r."),
                ("sam",    "What shifts the IS curve?"),
                ("oliver", "IS shifts right: fiscal expansion (G↑ or T↓), consumer/investor confidence ↑, net exports ↑."),
                ("maya",   "IS shifts left: fiscal contraction, confidence ↓, trade deficit worsening."),
                ("sam",    "And LM curve?"),
                ("nina",   "LM shifts right: money supply increases (Fed buys bonds). LM shifts left: money supply decreases."),
                ("oliver", "Equilibrium is where IS and LM intersect — gives equilibrium output (Y) and interest rate (r)."),
                ("maya",   "Crowding out effect: fiscal expansion shifts IS right, raises r, reduces private investment."),
                ("sam",    "So the multiplier is less than the simple Keynesian model suggests."),
                ("nina",   "Exactly. Higher r partially offsets the fiscal stimulus through investment crowding out."),
                ("oliver", "Unless we're in a liquidity trap — then LM is horizontal and no crowding out."),
            ],
            "current-events": [
                ("sam",    "How do the current Fed rate hikes fit into IS-LM?"),
                ("maya",   "Rate hikes = contractionary monetary policy = LM shifts left = higher r, lower Y."),
                ("nina",   "The goal is to reduce Y to bring inflation down via the AD curve."),
                ("oliver", "But it risks a recession if LM shifts too far left."),
                ("sam",    "The 'soft landing' debate — can the Fed reduce inflation without crashing output?"),
                ("maya",   "Historically it's very hard. 1981 Volcker disinflation caused a deep recession."),
                ("nina",   "Recent inflation looks supply-side too — oil shocks, supply chain. IS-LM doesn't capture that well."),
                ("oliver", "That's where AS-AD comes in. Supply shocks shift SRAS left: stagflation."),
                ("sam",    "Policy dilemma: if it's a supply shock, raising rates fights inflation but worsens output."),
                ("maya",   "Prof. Harrington talked about this — no good policy tool for stagflation."),
                ("nina",   "It's why the 1970s were so painful. Double-digit inflation and high unemployment."),
                ("oliver", "Modern monetary economists argue the models need updating for supply-side dynamics."),
            ],
            "problem-sets": [
                ("sam",    "PS3 help thread. Question 4: 'Fiscal expansion under fixed exchange rate.' Where to start?"),
                ("oliver", "That's Mundell-Fleming. Fixed exchange rate = BP curve is horizontal."),
                ("maya",   "With fixed exchange rates, monetary policy is ineffective. Fiscal policy is fully effective."),
                ("nina",   "Because: fiscal expansion shifts IS right → r tends to rise → capital inflows → currency appreciates → central bank buys foreign currency to maintain peg → money supply expands → LM shifts right."),
                ("sam",    "Oh so the LM adjustment happens automatically to maintain the peg."),
                ("oliver", "Exactly. Fiscal multiplier is 1/MPC in closed economy but larger in open with fixed rate."),
                ("maya",   "PS3 question 6: 'Derive the IS curve from goods market equilibrium.' Anyone done it?"),
                ("nina",   "Start from Y = C + I + G + NX. Substitute consumption function and investment function."),
                ("sam",    "C = a + b(Y-T), I = d - er. Substitute: Y = a + b(Y-T) + d - er + G + NX."),
                ("oliver", "Solve for r: r = [a + bY - bT + d + G + NX - Y(1-b)] / e."),
                ("maya",   "That gives r as a decreasing function of Y — the downward-sloping IS curve."),
                ("nina",   "PS4 is due Friday. Who wants to start a session Wednesday evening?"),
                ("sam",    "Wednesday 7pm works for me. Zoom or in person?"),
                ("oliver", "Let's do Zoom. I'll share my screen and we can work through it together."),
            ],
        },
        "reactions": {
            "general":        [("oliver", "👍"), ("maya",  "🎉")],
            "is-lm-models":   [("sam",    "🔥"), ("nina",  "👍")],
            "current-events": [("maya",   "😮"), ("oliver","👍")],
            "problem-sets":   [("nina",   "🎉"), ("sam",   "👍")],
        },
        "pins": {
            "general":        0,
            "is-lm-models":   0,
            "current-events": 2,
            "problem-sets":   1,
        },
    },
    {
        "name": "Hunter Philosophy Circle",
        "description": "Exploring the big questions together — epistemology, ethics, and metaphysics.",
        "school": "CUNY Hunter College",
        "course": "PHIL 101",
        "owner": "oliver",
        "members": ["zara", "maya", "jordan"],
        "channels": {
            "general": [
                ("oliver", "Welcome to the Hunter Philosophy Circle! Glad we're doing this."),
                ("zara",   "I've been wanting a philosophy discussion group forever. PHIL 101 doesn't go deep enough."),
                ("maya",   "Agreed. The textbook readings are interesting but class goes so fast."),
                ("jordan", "What's everyone's philosophical background? I'm pretty new to this."),
                ("oliver", "I've taken a few classes. Really into philosophy of mind lately."),
                ("zara",   "I came in through ethics — started reading Peter Singer and couldn't stop."),
                ("maya",   "I got hooked by Descartes' Meditations. The cogito blew my mind."),
                ("jordan", "Cogito ergo sum — I think therefore I am. We covered that in class."),
                ("oliver", "The cogito is actually more subtle than it first appears. Worth discussing!"),
                ("zara",   "Let's do a reading each week and discuss. Start with something accessible."),
                ("maya",   "Plato's Allegory of the Cave? Or something more contemporary?"),
                ("oliver", "Let's do the Cave this week, then move to something modern next week."),
                ("jordan", "I'll re-read it tonight. The prisoners and shadows thing."),
                ("zara",   "The Cave is so good. Plato packing so much epistemology into a story."),
            ],
            "ethics": [
                ("zara",   "Ethics thread! Let's start with the trolley problem."),
                ("maya",   "Classic. Utilitarian says pull the lever — save 5 at the cost of 1."),
                ("jordan", "But the footbridge variant is interesting — push a man off a bridge to stop the trolley."),
                ("oliver", "Same utilitarian calculus but most people feel differently about it."),
                ("zara",   "That's Judith Thomson's point. The means matter, not just the ends."),
                ("maya",   "Kantian ethics would say you can't use someone as a mere means — don't push."),
                ("jordan", "What about Singer's drowning child argument? You're walking past a pond, child drowning."),
                ("zara",   "Singer says you're obligated to save the child even at significant personal cost."),
                ("oliver", "And the implication extends to global poverty — we're all 'walking past the drowning child'."),
                ("maya",   "But most people resist that conclusion. Does proximity matter morally?"),
                ("zara",   "Singer says no — suffering is suffering regardless of distance. Hard to argue against."),
                ("jordan", "Yet almost no one acts consistently on Singer's principle. What does that say?"),
                ("oliver", "Bernard Williams said utilitarianism alienates us from our 'ground projects' — the things that give our lives meaning."),
                ("maya",   "So there's a tension between impartial morality and personal integrity. Deep stuff."),
                ("zara",   "For next week: let's read Thomson's 'Violinist' argument about bodily autonomy."),
            ],
            "epistemology": [
                ("oliver", "Epistemology time! Starting point: what can we actually know?"),
                ("maya",   "Descartes in Meditation I: doubt everything. Senses can deceive, we might be dreaming."),
                ("zara",   "The evil demon hypothesis — an all-powerful deceiver could make us believe falsehoods."),
                ("jordan", "That sounds like the Matrix. Were they inspired by Descartes?"),
                ("oliver", "The Wachowskis definitely drew on Descartes and Baudrillard's Simulacra."),
                ("maya",   "And then the cogito: even if I'm deceived, the act of thinking proves I exist."),
                ("zara",   "Descartes uses this to rebuild knowledge from scratch — a foundationalist approach."),
                ("oliver", "But Hume later attacks the foundations. Induction can't be justified without circular reasoning."),
                ("jordan", "The problem of induction — just because the sun rose every day doesn't prove it will rise tomorrow."),
                ("maya",   "Hume's skepticism is more radical than Descartes'. No bedrock certainty at all?"),
                ("zara",   "Kant's response: we impose structure on experience. Space, time, causality are frameworks we bring."),
                ("oliver", "Ship of Theseus fits here too — is it the same ship after every plank is replaced?"),
                ("maya",   "Leibniz's Law: two things are identical iff they share all properties. The new ship differs."),
                ("jordan", "But we call it the same ship by convention. Parfit's personal identity work extends this."),
                ("zara",   "Parfit's Reasons and Persons: personal identity might not be what matters for survival."),
                ("oliver", "The teleportation thought experiment — if you're disassembled and reassembled, is it you?"),
                ("maya",   "Psychological continuity theory says yes, if memories and personality are preserved."),
            ],
        },
        "reactions": {
            "general":     [("zara",   "🎉"), ("maya",  "👍")],
            "ethics":      [("jordan", "😮"), ("oliver","🔥")],
            "epistemology":[("maya",   "🔥"), ("zara",  "😮")],
        },
        "pins": {
            "general":      0,
            "ethics":       4,
            "epistemology": 0,
        },
    },
]

USER_DMS = [
    {
        "from": "maya",
        "to":   "jordan",
        "messages": [
            ("maya",   "Hey Jordan! Are we still on for the calc study session Thursday?"),
            ("jordan", "Definitely! I was going to review related rates beforehand. Should I bring practice problems?"),
            ("maya",   "Yes please! Bring the ones from chapter 4. I'll bring my notes from Prof. Kim's office hours."),
            ("jordan", "Perfect. Should we grab food first or start at 6 sharp?"),
            ("maya",   "Let's aim for 6pm sharp — I have to catch the A train back by 10."),
            ("jordan", "Works for me. See you at Bobst! I'll grab a coffee on the way."),
        ],
    },
    {
        "from": "alex",
        "to":   "priya",
        "messages": [
            ("alex",  "Hey Priya, did you push your BST implementation to the shared repo?"),
            ("priya", "Just pushed it! Branch is called 'bst-priya'. The delete method needs review."),
            ("alex",  "Looking at it now. Your two-children case looks good but the inorder successor search has a small off-by-one."),
            ("priya", "Ah I see it — I return current instead of current.left at the end. Fix pushed."),
            ("alex",  "Perfect! All tests pass now. We should combine our implementations for the final project."),
            ("priya", "Agreed. Let's sync Saturday after the group call and write the merge sort extension together."),
        ],
    },
]


class Command(BaseCommand):
    help = "Seed local sample communities; optionally add DMs to one guest-owned community."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--guest-community", type=int)

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        if not settings.DEBUG:
            raise CommandError("Sample data can only be seeded with DJANGO_DEBUG=true.")

        users = {}
        for handle, display_name in PEOPLE.items():
            user, created = get_user_model().objects.get_or_create(
                username=f"studyspot_sample_{handle}"
            )
            if created:
                user.set_unusable_password()
                user.save(update_fields=["password"])
            Account.objects.get_or_create(
                user=user,
                defaults={"username": display_name, "account_type": AccountType.STUDENT},
            )
            users[handle] = user

        for group in GROUPS:
            owner_key = group["owner"]
            community, _ = Community.objects.get_or_create(
                name=group["name"],
                owner=users[owner_key],
                defaults={
                    "description": group["description"],
                    "school": group["school"],
                    "course": group["course"],
                },
            )
            Membership.objects.get_or_create(community=community, user=users[owner_key])
            for member_key in group["members"]:
                Membership.objects.get_or_create(community=community, user=users[member_key])

            for position, (channel_name, msg_list) in enumerate(group["channels"].items()):
                channel, _ = Channel.objects.get_or_create(
                    community=community,
                    name=channel_name,
                    defaults={"position": position},
                )
                created_msgs = []
                for author_key, content in msg_list:
                    msg, _ = Message.objects.get_or_create(
                        channel=channel,
                        author=users[author_key],
                        content=content,
                        defaults={"author_name": PEOPLE[author_key]},
                    )
                    created_msgs.append((author_key, msg))

                # Reactions
                reaction_pairs = group.get("reactions", {}).get(channel_name, [])
                for idx, (reactor_key, emoji) in enumerate(reaction_pairs):
                    if idx < len(created_msgs):
                        _, target_msg = created_msgs[idx]
                        Reaction.objects.get_or_create(
                            message=target_msg,
                            emoji=emoji,
                            user=users[reactor_key],
                            defaults={},
                        )

                # Pinned message
                pin_index = group.get("pins", {}).get(channel_name, 0)
                if created_msgs and pin_index < len(created_msgs):
                    _, pin_msg = created_msgs[pin_index]
                    if not pin_msg.pinned_at:
                        pin_msg.pinned_at = timezone.now()
                        pin_msg.save(update_fields=["pinned_at"])

        # Seed account-to-account DMs
        for dm_spec in USER_DMS:
            from_user = users[dm_spec["from"]]
            to_user = users[dm_spec["to"]]
            from_key = f"u:{from_user.pk}"
            to_key = f"u:{to_user.pk}"
            first, second = sorted((from_key, to_key))
            first_name = PEOPLE[dm_spec["from"]] if first == from_key else PEOPLE[dm_spec["to"]]
            second_name = PEOPLE[dm_spec["from"]] if second == from_key else PEOPLE[dm_spec["to"]]
            conversation, _ = DirectConversation.objects.get_or_create(
                pair_key=hashlib.sha256(f"{first}\0{second}".encode()).hexdigest(),
                defaults={
                    "first_key": first,
                    "second_key": second,
                    "first_name": first_name,
                    "second_name": second_name,
                },
            )
            for sender_key, content in dm_spec["messages"]:
                sender_user = users[sender_key]
                sender_account_key = f"u:{sender_user.pk}"
                DirectMessage.objects.get_or_create(
                    conversation=conversation,
                    sender_key=sender_account_key,
                    content=content,
                    defaults={"author_name": PEOPLE[sender_key]},
                )

        # Guest community DM seeding
        guest_community_id = options["guest_community"]
        if guest_community_id is not None:
            community = Community.objects.filter(pk=guest_community_id, owner__isnull=True).first()
            if community is None:
                raise CommandError("Choose an existing guest-owned community.")
            guests = list(
                GuestMembership.objects.filter(
                    community=community, expires_at__gt=timezone.now()
                ).values_list("guest_id", flat=True)
            )
            if len(guests) != 1:
                raise CommandError("The guest-owned community must have exactly one active guest.")
            guest_key = f"g:{guests[0]}"
            channel = community.channels.order_by("position", "id").first()
            if channel is None:
                raise CommandError("The guest-owned community has no channel.")
            for handle, content, dm_text in (
                (
                    "maya",
                    "I can help review the first practice set.",
                    "Want to plan a study session?",
                ),
                (
                    "jordan",
                    "I am working through the exam outline.",
                    "I shared an exam outline in the channel.",
                ),
            ):
                user = users[handle]
                Membership.objects.get_or_create(community=community, user=user)
                Message.objects.get_or_create(
                    channel=channel,
                    author=user,
                    content=content,
                    defaults={"author_name": PEOPLE[handle]},
                )
                account_key = f"u:{user.pk}"
                first, second = sorted((account_key, guest_key))
                conversation, _ = DirectConversation.objects.get_or_create(
                    pair_key=hashlib.sha256(f"{first}\0{second}".encode()).hexdigest(),
                    defaults={
                        "first_key": first,
                        "second_key": second,
                        "first_name": PEOPLE[handle] if first == account_key else "You",
                        "second_name": PEOPLE[handle] if second == account_key else "You",
                    },
                )
                DirectMessage.objects.get_or_create(
                    conversation=conversation,
                    sender_key=account_key,
                    content=dm_text,
                    defaults={"author_name": PEOPLE[handle]},
                )

        self.stdout.write(self.style.SUCCESS("Sample communities and conversations are ready."))
