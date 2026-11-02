# Sources and interpretation

Access checked on **2 November 2026**. This project uses public Australian Bureau of Statistics (ABS) aggregate statistics. Both XLSX downloads returned HTTP 200 without credentials. The project contains descriptive analysis of approvals and revisions; the repository name is not evidence of a housing slump.

## Official release vintages

The source is **Table 09, Number of dwelling units approved, original, states and territories**, from *Building Approvals, Australia*.

| Reference period | Official release page | Initial publication | Direct Table 09 download |
| --- | --- | --- | --- |
| August 2026 | [August release](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/aug-2026) | 30 September 2026 | [8731009.xlsx](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/aug-2026/8731009.xlsx) |
| September 2026 | [September release](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/sep-2026) | 2 November 2026, 11:30 am AEDT | [8731009.xlsx](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/sep-2026/8731009.xlsx) |

The August page shows an additional timestamp of **7 October 2026, 11:30 am AEDT**. Its post-release changes section identifies that update as the supplementary small-area release. The September release was also verified through the [latest-release page](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/latest-release), which will change with future publications.

These are files retrieved from release-specific URLs on the access date, not independently archived copies of the first published bytes. HTTP `Last-Modified` and workbook creation timestamps are technical metadata, not proof of public availability. Preserve the retrieval time and content digest alongside the release reference period.

## Observed file contract

The following metadata was read directly from the downloaded workbooks, independently of the application parser.

| Property | August file | September file |
| --- | --- | --- |
| Download size | 136,911 bytes | 137,102 bytes |
| Monthly rows per series | 518 | 519 |
| First reference month | July 1983 | July 1983 |
| Last reference month | August 2026 | September 2026 |
| Series count | 27 | 27 |
| SHA-256 | `8c50ade7c0c76eeda8c42183c66126a77ac628440b76a3fbc000557ead8b640c` | `af24371758b3dc7ebf012af99d22ee6e54da0d0c2139eaba5b174bd48e851f25` |

The `Data1` worksheet contains one month in column A and one series per column B–AB. Row 1 contains descriptions; rows 2–10 contain unit, series type, data type, frequency, collection month, start, end, observation count and series ID. Observations begin at row 11; Excel dates represent reference months.

All 27 series have unit `Number`, series type `Original`, data type `FLOW` and frequency `Month`. There are nine geographies: Australia, NSW, Victoria, Queensland, South Australia, Western Australia, Tasmania, Northern Territory and ACT. Each has three categories: `Houses`, `Dwellings excluding houses`, and `Total (Type of Building)`. They describe dwelling units, not the number of approval documents. These are total-sector counts, not private-sector-only counts. Preserve the ABS series ID as source identity.

An observation's logical identity is **release vintage × series ID × reference month**. A later vintage can change an already observed month. Do not treat the release reference month as the observation month for every row.

An independent arithmetic check of each workbook found **36 mismatches across 17 reference months, November 1983–November 2010**. The same mismatches occur in both vintages. Checks compare eight state/territory components with Australia, and houses plus dwellings excluding houses with published total dwellings for each geography. For example, November 1983 state house counts sum to 10,465 against Australia's 10,468. In November 2010, NSW's two dwelling categories sum to 3,282 against its total of 3,283, and Australia's sum to 14,762 against 14,763. No such mismatch was found after November 2010 in either file. These are source observations, not a diagnosis of their cause: retain published values and expose quality flags instead of silently changing them or rejecting the whole archive.

## Why this release matters

The September publication arrived on the project's build date. Its headline reports a **5.1% monthly rise to 17,948 total dwelling approvals, seasonally adjusted**, while state movements differ. That establishes a timely monitoring question, not a uniform slump. These headline figures are context from the [September release](https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/sep-2026), **not the original series ingested here**.

For a direct workbook cross-check, September Table 09 records **18,318** original Australian approvals: **11,378 houses** plus **6,940 dwellings excluding houses**. August's own workbook records **16,968** original Australian approvals for August. Comparing different vintages' newest months can mix revisions with movement; calculate growth within one vintage and compare revisions for the same series and month across vintages.

## Definitions and limitations

The [September 2026 methodology](https://www.abs.gov.au/methodologies/building-approvals-australia-methodology/sep-2026) explains that building approvals authorise construction to begin; preliminary planning permissions are excluded. Approvals are not starts, completions, available homes or net additions to housing stock. The collection includes residential building valued at $10,000 or more and non-residential building valued at $50,000 or more under its current coverage rules.

Administrative reporting delays, corrections and newly identified records cause revisions. Census coverage does not eliminate reporting or coverage errors. Original series retain seasonality and calendar effects; a monthly percentage is not a seasonally adjusted economic signal. ABS cautions that historical state components and Australian totals can differ in some months from July 1983 to July 1985. Jervis Bay is included with NSW, and Christmas Island and Cocos (Keeling) Islands with WA, from July 2002. Preserve published Australian totals rather than silently reconstructing them from states.

For aggregation, select either Australia or its state/territory components; summing both double-counts geography. Likewise, select either total dwellings or its two component categories. Missing or suppressed values must remain distinguishable from zero. Two release snapshots demonstrate observed revisions, not the complete publication history. This dataset alone cannot identify interest-rate effects, explain housing affordability, forecast construction or establish why approvals changed.

## Reuse and attribution

The [ABS copyright policy](https://www.abs.gov.au/website-privacy-copyright-and-disclaimer#copyright-and-creative-commons), checked on the access date, provides website material under [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/) with specified exceptions, including logos, the Coat of Arms, trademarks, microdata and third-party content. This project uses ABS aggregate statistical tables; it does not grant rights to those excluded materials. Attribute the ABS, link the source and licence, and identify transformations. No ABS endorsement is claimed.

Suggested attribution for this project's transformed data and analysis:

> Source: Australian Bureau of Statistics, *Building Approvals, Australia*, August and September 2026, Table 09, accessed 2 November 2026. © Commonwealth of Australia. Licensed under CC BY 4.0. Data reshaped and comparisons calculated by this project; the ABS has not endorsed these outputs.

The [ABS citation guide](https://www.abs.gov.au/how-cite-abs-sources) recommends reference-period-specific links and an access date. Retain the release links above in redistributed outputs. The repository's software licence applies to project code; source data retains its own attribution and licence conditions.
