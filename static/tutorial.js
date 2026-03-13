/**
 * Dashboard overlay tutorial — first-run guided tour.
 * Uses localStorage to track whether the user has seen it.
 */

const TUTORIAL_KEY = 'betty_tutorial_seen';

const TUTORIAL_STEPS = [
  {
    // Step 0: Welcome (centred, no target)
    target: null,
    title: 'Welcome to Betty',
    body: 'Betty is an AI voice companion that proactively calls truck drivers when safety systems detect fatigue, erratic driving, or approaching break limits.<br><br>This quick tour will walk you through the dashboard.',
    position: 'center',
  },
  {
    target: '#card-drivers',
    title: 'Driver Fleet',
    body: 'Your active drivers are listed here with their <strong>current route</strong>, <strong>hours driven</strong>, <strong>time until mandatory break</strong>, and recent safety events. Status badges show whether a driver is idle or on a call with Betty.',
    position: 'right',
  },
  {
    target: '#card-call-status',
    title: 'Call Status',
    body: 'When Betty calls a driver, this panel shows the <strong>live call timer</strong> and connection status. You can end a call from here if needed.',
    position: 'left',
  },
  {
    target: '#card-triggers',
    title: 'Trigger Controls',
    body: 'This is where you simulate safety events. Select a driver, choose an event type (fatigue, erratic driving, break limit), and fire the trigger. Betty will assess the risk and call the driver.<br><br><strong>Simulation Mode</strong> is on by default — an AI driver persona responds so no microphone is needed.',
    position: 'right',
  },
  {
    target: '#card-shift',
    title: 'Shift Simulation',
    body: 'Run a compressed <strong>14-hour shift</strong> with multiple random events. Betty will call the driver repeatedly with escalating triggers, demonstrating cross-call memory and escalation behaviour.',
    position: 'left',
  },
  {
    target: '#card-transcript',
    title: 'Live Transcription',
    body: 'During an active call, the <strong>real-time conversation transcript</strong> appears here. You can follow what Betty and the driver are saying as the call progresses.',
    position: 'right',
  },
  {
    target: '#card-generator',
    title: 'Card Generator',
    body: 'Generate sample visual cards: <strong>rest stop recommendations</strong> with AI-generated scenic backgrounds (Imagen 4), <strong>shift wellness summaries</strong>, and <strong>incident reports</strong> for the fleet manager.',
    position: 'left',
  },
  {
    target: '#card-visuals',
    title: 'Visual Cards',
    body: 'Generated cards appear here. Rest stop cards use <strong>Gemini Flash + Google Search</strong> to describe the real location, then <strong>Imagen 4</strong> generates a scenic background photograph. Click any card to view full-size.',
    position: 'top',
  },
  {
    target: '#card-event-log',
    title: 'Event Log',
    body: 'A detailed log of all system events — triggers, calls, transcripts, escalations, and card generation. Useful for monitoring the full flow.',
    position: 'top',
  },
  {
    // Final step: no target
    target: null,
    title: 'Ready to Go',
    body: 'Try triggering a <strong>fatigue event</strong> to see Betty in action. Select a driver, choose an event type, and click the trigger button.<br><br>You can restart this tour anytime using the <strong>Restart Tour</strong> button in the header.',
    position: 'center',
  },
];

let tutorialStep = 0;
let tutorialActive = false;
let prevHighlight = null;

function startTutorial() {
  tutorialStep = 0;
  tutorialActive = true;
  const overlay = document.getElementById('tutorial-overlay');
  overlay.style.display = '';
  overlay.classList.add('visible');
  renderTutorialStep();
}

function endTutorial() {
  tutorialActive = false;
  const overlay = document.getElementById('tutorial-overlay');
  overlay.style.display = 'none';
  overlay.classList.remove('visible');
  clearHighlight();
  localStorage.setItem(TUTORIAL_KEY, '1');
}

function tutorialNext() {
  if (tutorialStep >= TUTORIAL_STEPS.length - 1) {
    endTutorial();
    return;
  }
  tutorialStep++;
  renderTutorialStep();
}

function tutorialPrev() {
  if (tutorialStep <= 0) return;
  tutorialStep--;
  renderTutorialStep();
}

function clearHighlight() {
  if (prevHighlight) {
    prevHighlight.classList.remove('tutorial-highlight');
    prevHighlight = null;
  }
}

function renderTutorialStep() {
  const step = TUTORIAL_STEPS[tutorialStep];
  const tooltip = document.getElementById('tutorial-tooltip');
  const title = document.getElementById('tutorial-title');
  const body = document.getElementById('tutorial-body');
  const prevBtn = document.getElementById('tutorial-btn-prev');
  const nextBtn = document.getElementById('tutorial-btn-next');
  const indicator = document.getElementById('tutorial-step-indicator');

  // Update content
  title.textContent = step.title;
  body.innerHTML = step.body;

  // Step indicator dots
  indicator.innerHTML = TUTORIAL_STEPS.map((_, i) => {
    const cls = i < tutorialStep ? 'done' : i === tutorialStep ? 'active' : '';
    return `<div class="tutorial-dot ${cls}"></div>`;
  }).join('');

  // Button visibility
  prevBtn.style.display = tutorialStep === 0 ? 'none' : '';
  nextBtn.textContent = tutorialStep === TUTORIAL_STEPS.length - 1 ? 'Get Started' : 'Next';

  // Clear previous highlight
  clearHighlight();

  // Remove all arrow classes
  tooltip.classList.remove('arrow-top', 'arrow-bottom', 'arrow-left', 'arrow-right', 'arrow-none', 'tutorial-welcome');

  if (!step.target || step.position === 'center') {
    // Centred tooltip, no highlight
    tooltip.classList.add('arrow-none', 'tutorial-welcome');
    tooltip.style.top = '';
    tooltip.style.left = '';
    tooltip.style.transform = '';
    return;
  }

  // Highlight target element
  const target = document.querySelector(step.target);
  if (!target) return;

  target.classList.add('tutorial-highlight');
  prevHighlight = target;

  // Scroll target into view
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // Position tooltip after scroll settles
  setTimeout(() => positionTooltip(tooltip, target, step.position), 350);
}

function positionTooltip(tooltip, target, position) {
  const rect = target.getBoundingClientRect();
  const ttWidth = tooltip.offsetWidth;
  const ttHeight = tooltip.offsetHeight;
  const margin = 16;

  // Remove transform from welcome mode
  tooltip.style.transform = '';
  tooltip.classList.remove('tutorial-welcome');

  let top, left;

  switch (position) {
    case 'right':
      top = rect.top + rect.height / 2 - ttHeight / 2;
      left = rect.right + margin;
      tooltip.classList.add('arrow-left');
      // If overflows right, put it below instead
      if (left + ttWidth > window.innerWidth - 20) {
        top = rect.bottom + margin;
        left = rect.left;
        tooltip.classList.remove('arrow-left');
        tooltip.classList.add('arrow-top');
      }
      break;

    case 'left':
      top = rect.top + rect.height / 2 - ttHeight / 2;
      left = rect.left - ttWidth - margin;
      tooltip.classList.add('arrow-right');
      // If overflows left, put it below instead
      if (left < 20) {
        top = rect.bottom + margin;
        left = rect.left;
        tooltip.classList.remove('arrow-right');
        tooltip.classList.add('arrow-top');
      }
      break;

    case 'top':
      top = rect.top - ttHeight - margin;
      left = rect.left + rect.width / 2 - ttWidth / 2;
      tooltip.classList.add('arrow-bottom');
      // If overflows top, put it below
      if (top < 20) {
        top = rect.bottom + margin;
        tooltip.classList.remove('arrow-bottom');
        tooltip.classList.add('arrow-top');
      }
      break;

    case 'bottom':
    default:
      top = rect.bottom + margin;
      left = rect.left + rect.width / 2 - ttWidth / 2;
      tooltip.classList.add('arrow-top');
      break;
  }

  // Clamp to viewport
  top = Math.max(10, Math.min(top, window.innerHeight - ttHeight - 10));
  left = Math.max(10, Math.min(left, window.innerWidth - ttWidth - 10));

  tooltip.style.top = top + 'px';
  tooltip.style.left = left + 'px';
}

// Reposition on scroll/resize
window.addEventListener('resize', () => {
  if (!tutorialActive) return;
  renderTutorialStep();
});

// Keyboard navigation
document.addEventListener('keydown', (e) => {
  if (!tutorialActive) return;
  if (e.key === 'Escape') endTutorial();
  if (e.key === 'ArrowRight' || e.key === 'Enter') tutorialNext();
  if (e.key === 'ArrowLeft') tutorialPrev();
});

// Auto-start on first visit
if (!localStorage.getItem(TUTORIAL_KEY)) {
  // Small delay so the dashboard renders first
  setTimeout(startTutorial, 500);
}
