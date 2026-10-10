// Content for the public landing page (src/pages/Landing.jsx).
// Edit this file to change contact details, team names, and resource links
// without touching the page layout.

export const SITE = {
  name: 'Nigraan AI',
  repoUrl: 'https://github.com/zoraizz/nigraan-ai',

  // Shown in the Contact column only when set, e.g. 'team@example.com'.
  // Left empty on purpose: no placeholder address is displayed.
  contactEmail: '',

  // Shown in the About column only when filled, e.g.
  // [{ name: 'Full Name', role: 'Machine learning' }].
  team: [],
}

export const RESOURCES = [
  {
    label: 'Source code on GitHub',
    note: 'Every module, test and design decision.',
    href: SITE.repoUrl,
  },
  {
    label: 'API contract',
    note: 'Request and response shapes for all three services.',
    href: `${SITE.repoUrl}/blob/main/API_CONTRACT.md`,
  },
  {
    label: 'NDMA Pakistan',
    note: 'The authority whose hazard reports shaped our coverage.',
    href: 'https://ndma.gov.pk',
  },
  {
    label: 'Open-Meteo',
    note: 'Free weather API behind the live town-coordinate weather context.',
    href: 'https://open-meteo.com',
  },
  {
    label: 'xBD building damage dataset',
    note: 'Labelled satellite tiles used to train the damage model.',
    href: 'https://xview2.org',
  },
  {
    label: 'Pakistan 2022 flood imagery study',
    note: 'Source of the Pakistan flood tiles added in model v3.',
    href: 'https://doi.org/10.34133/remotesensing.0733',
  },
]

export const FLOOD_2022_SOURCE = {
  label: 'via ReliefWeb, November 2022',
  href: 'https://reliefweb.int/report/pakistan/pakistan-floods-update-dg-echo-ndma-who-echo-daily-flash-28-november-2022',
}
