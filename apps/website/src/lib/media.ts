const evidence =
  "https://github.com/MarkUnthank/flyhard/tree/main/reports/2026-09-09-clean-videos";

// Newest entries first. Keep IDs stable so shared links keep pointing to an entry.
export const mediaEntries = [
  {
    id: "faster-steering",
    number: "02",
    date: "2026-09-09",
    dateLabel: "9 September 2026",
    category: "Steering experiment",
    title: "A little too much ambition.",
    intro: "Same tiny brain. A much faster request. This time, the road wins.",
    duration: "14 seconds",
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
