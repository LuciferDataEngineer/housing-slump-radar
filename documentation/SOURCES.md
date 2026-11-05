# Sources, licences and the pinned copies

Accessed **5 November 2026**. Every file under `data/raw/` is the exact download listed here. `housing-radar verify` checks the SHA-256. `housing-radar fetch` tries the publisher URL first and does not replace a pinned file unless the hash matches, or you pass `--update`.

No account, key or paid API is required. The static dashboard is computed only from these files.

## Reserve Bank of Australia

| File | Series | URL |
| --- | --- | --- |
| `data/raw/rba/f1-data.csv` | Table F1, daily cash rate target `FIRMMCRTD` | https://www.rba.gov.au/statistics/tables/csv/f1-data.csv |
| `data/raw/rba/f5-data.csv` | Table F5, indicator lending rates. Discounted owner-occupier variable is `FILRHLBVD` | https://www.rba.gov.au/statistics/tables/csv/f5-data.csv |

F1 was published 5 November 2026 and includes the target of 4.85% on 4 November. F5 was published 8 October 2026 and its latest month is September 2026. The change column on F1 is blank for 30 September 2026 even though the target level moves from 4.35% to 4.60% that day. The pipeline derives the step from the level.

RBA statistical tables are free to reuse with acknowledgement. Canstar is named inside F5 as an upstream source for some lending-rate columns. The RBA has not endorsed this project.

Decision statement: [Media release 2026-30, 3 November 2026](https://www.rba.gov.au/media-releases/2026/mr-26-30.html). The target took effect on 4 November, which is the date in table F1.

## Australian Bureau of Statistics

Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The ABS has not endorsed this project.

| File | Series | URL |
| --- | --- | --- |
| `data/raw/abs/res_dwell_st.csv` | Residential dwellings: value, number and mean price by state. Dataflow `RES_DWELL_ST` from 2018 | https://data.api.abs.gov.au/rest/data/ABS,RES_DWELL_ST/all?startPeriod=2018&format=csvfile |
| `data/raw/abs/lend_housing.csv` | Lending indicators, housing, new commitments. Dataflow `LEND_HOUSING` from 2023-Q1 | https://data.api.abs.gov.au/rest/data/ABS,LEND_HOUSING/all?startPeriod=2023-01&format=csvfile |
| `data/raw/abs/8731009-aug-2026.xlsx` | Building Approvals Table 09, August 2026 vintage. SHA-256 `8c50ade7c0c76eeda8c42183c66126a77ac628440b76a3fbc000557ead8b640c` | https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/aug-2026/8731009.xlsx |
| `data/raw/abs/8731009-sep-2026.xlsx` | Building Approvals Table 09, September 2026 vintage. SHA-256 `af24371758b3dc7ebf012af99d22ee6e54da0d0c2139eaba5b174bd48e851f25` | https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/sep-2026/8731009.xlsx |

Mean price is measure 5. Counts are in thousands in the API and are scaled back to dwellings. Lending values use the API unit multiplier and are stored in dollars. The commitment slice is total dwellings excluding refinancing, all lender types, original and seasonally adjusted, for owner-occupiers, investors and the total.

Table 09 is the original (not seasonally adjusted) count of dwelling units. The supply domain keeps both vintages so a revision of an old month is not confused with a new month. Houses plus other dwellings, and the states plus territories, are checked against the published totals. Mismatches before 2011 are kept as quality rows. None were found from January 2011 onward in either vintage.

The ABS Indicator API returned HTTP 403 to this client. The Data API above worked with no key.

## Victorian Government

Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Publisher: Department of Transport and Planning / Valuer-General Victoria. Catalogue:

- [Annual median house prices by suburb](https://discover.data.vic.gov.au/dataset/victorian-property-sales-report-median-house-by-suburb-time-series)
- [Quarterly median house prices by suburb](https://discover.data.vic.gov.au/dataset/victorian-property-sales-report-median-house-by-suburb)

| File | What it is | Official URL | Pinned from |
| --- | --- | --- | --- |
| `data/raw/datavic/houses-by-suburb-2015-2025.xlsx` | Annual medians, 2015–2025 | https://www.land.vic.gov.au/__data/assets/excel_doc/0033/775617/houses-by-suburb-2015-2025.xlsx | Wayback capture of that URL on 20 October 2026 |
| `data/raw/datavic/median-house-march-quarter-2026.xls` | Quarterly medians through the March quarter 2026 | https://www.land.vic.gov.au/__data/assets/excel_doc/0037/777961/median-house-march-quarter-2026.xls | Wayback capture of that URL on 4 October 2026 |

On 5 November 2026 the official host returned HTTP 403 to this client. The fetch script still tries the official URL first, then the Wayback URL. The dashboard uses the quarterly file because it is the later release. A `^` or `*` flag means fewer than 10 sales, or a carried-forward zero, and those suburbs are left out of the ranking.

## News that is cited and not plotted

These are not inputs to the charts.

- [ABC, 2 November 2026](https://www.abc.net.au/news/2026-11-02/house-prices-fall-in-october-biggest-downturn-40-years-cotality/107325214), reporting Cotality: national values −1.2% in October, about 6.7% and $63,000 under the March peak, capital cities −8.1% in seven months. Cotality's own note the same day said sales over three months were about 23% lower than a year earlier: [Cotality, 2 November 2026](https://www.cotality.com/au/insights/articles/housing-downturn-broadens-as-brisbane-and-perth-lead-the-decline).
- [Australian Broker, 2 November 2026](https://www.brokernews.com.au/news/breaking-news/home-values-fall-for-seventh-month-as-indices-split-on-depth-290239.aspx) records that PropTrack published a smaller October fall. The dashboard says so, and does not pick a private index as the chart.
- [ABC, 3 November 2026](https://www.abc.net.au/news/2026-11-03/rba-interest-rates-markets-live-coverage/107338216) on the cash-rate decision. The rate used in the model is the RBA table, not the news article.

Cotality and CoreLogic are not scraped.
