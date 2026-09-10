const evidence =
  "https://github.com/MarkUnthank/flyhard/tree/main/reports/2026-09-09-clean-videos";

// Newest entries first. Keep IDs stable so shared links keep pointing to an entry.
type MediaEntry = {
  id: string;
  number: string;
  date: string;
  dateLabel: string;
  category: string;
  title: string;
  intro: string;
  duration: string;
  playback: string;
  paragraphs: string[];
  facts: string[];
  evidenceUrl: string;
  evidenceLabel: string;
  stills?: { file: string; caption: string }[];
};

export const mediaEntries: MediaEntry[] = [
  {
    id: "roundabout",
    number: "03",
    date: "2026-09-10",
    dateLabel: "10 September 2026",
    category: "Roundabout experiment",
    title: "A turn for the ambitious.",
    intro: "A roundabout, an indicator, and seven sponsors along for the ride.",
    duration: "25 seconds",
    playback: "Slow motion · 60 fps",
    paragraphs: [
      "The fly takes on the roundabout. Get a closer look from inside the cabin as it works the indicator stalk, turns the wheel, and cancels the signal, with our sponsors riding on the Mini.",
      "This slow-motion cut gives each moment room to breathe, including contact with traffic. Navigation and speed are still engineered inputs; the experiment continues.",
    ],
    facts: [
      "Steering & indicator sequence",
      "Seven sponsors on the Mini",
      "25-second slow-motion cut",
    ],
    evidenceUrl:
      "https://github.com/MarkUnthank/flyhard/tree/main/reports/2026-09-10-roundabout-media",
    evidenceLabel: "Recording notes & video verification",
    stills: [
      {
        file: "roundabout-arrival.jpg",
        caption: "The sponsors arrive at the roundabout.",
      },
      {
        file: "roundabout-indicator.jpg",
        caption: "A closer look at the indicator.",
      },
      {
        file: "roundabout-cabin.jpg",
        caption: "Inside the cabin as the fly cancels the signal.",
      },
    ],
  },
  {
    id: "faster-steering",
    number: "02",
    date: "2026-09-09",
    dateLabel: "9 September 2026",
    category: "Steering experiment",
    title: "A little too much ambition.",
    intro: "Same tiny brain. A much faster request. This time, the road wins.",
    duration: "14 seconds",
    playback: "Normal simulation speed",
    paragraphs: [
      "We kept the learned steering controller and increased the scripted speed and turn requests. The model moves the fly’s left foreleg, the leg turns a passive wheel through an assisted grip, and the measured wheel angle steers the car.",
      "The result includes contact with a parked motorcycle and then a pole. This controller has no camera input or learned road awareness. It can follow steering requests; choosing safe requests from the road is still ahead.",
      "This is the first 14 seconds of a 24-second run, played at normal simulation speed. The stationary tail is omitted. The road, neural activity, and fly body all follow the same recorded clock.",
    ],
    facts: [
      "Same steering controller",
      "Scripted speed & turns",
      "Both collisions retained",
    ],
    evidenceUrl: `${evidence}/carla-new-yorker-v1`,
    evidenceLabel: "Faster run: metrics, validation & export details",
  },
  {
    id: "calm-steering",
    number: "01",
    date: "2026-09-09",
    dateLabel: "9 September 2026",
    category: "Steering experiment",
    title: "Small turns. A real start.",
    intro:
      "From a neural model to a moving leg, a turning wheel, and a car that follows.",
    duration: "24 seconds",
    playback: "Normal simulation speed",
    paragraphs: [
      "Our first calm recording puts the pieces side by side: the view from CARLA, the model’s neural activity, and the simulated fly at its wheel. The learned policy controls the left foreleg. The right foreleg follows the wheel through a passive supporting grip.",
      "In this run, the car travels 45.58 metres with no collisions. Replaying the saved neural actions reproduces the recorded joint positions and commands exactly. Disabling the grip reduces peak steering by more than 99.97%, helping establish that the leg-to-wheel connection causes the turn.",
      "Speed and requested turn angles are scripted. This demonstrates the recorded steering chain, rather than autonomous driving. The next challenge is learning what to do from what is on the road.",
    ],
    facts: [
      "600 recorded frames",
      "45.58 metres travelled",
      "0 collisions in this run",
    ],
    evidenceUrl: `${evidence}/carla-calm-v2`,
    evidenceLabel: "Calm run: metrics, validation & grip comparison",
  },
];
