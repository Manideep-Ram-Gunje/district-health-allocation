# Reconciliation Report

NFHS-5 (2019-21) districts matched to Census 2011 districts.

## Coverage

| Metric | Value |
|---|---|
| NFHS-5 districts | 705 |
| Matched to a Census district | 705 (100.0%) |
| Unmatched (excluded from allocation) | 0 (0.0%) |
| Sharing a parent (post-2011 split) | 118 |

## Resolution tier

| Tier | Districts |
|---|---|
| `fuzzy` | 626 |
| `override:child_of` | 69 |
| `override:rename` | 7 |
| `fuzzy_review` | 3 |

Thresholds: accept >= 90, flag for review >= 80, reject below 80. Scorer: `rapidfuzz.fuzz.token_sort_ratio` over state-restricted candidate pools.

## Population apportionment

118 NFHS districts resolve to a Census parent shared with at least one sibling — these are post-2011 splits. Parent population is divided EQUALLY among children. This is unbiased in aggregate but wrong for any individual district, and it is the single largest source of error in the population denominator. Districts affected:

| NFHS state | NFHS district | Census parent | Siblings | Apportioned pop |
|---|---|---|---|---|
| Telangana | Adilabad | Adilabad | 4 | 685,310 |
| Telangana | Komaram Bheem Asifabad | Adilabad | 4 | 685,310 |
| Telangana | Mancherial | Adilabad | 4 | 685,310 |
| Telangana | Nirmal | Adilabad | 4 | 685,310 |
| Telangana | Jagitial | Karimnagar | 4 | 944,067 |
| Telangana | Karimnagar | Karimnagar | 4 | 944,067 |
| Telangana | Peddapalli | Karimnagar | 4 | 944,067 |
| Telangana | Rajanna Sircilla | Karimnagar | 4 | 944,067 |
| Telangana | Bhadradri Kothagudem | Khammam | 2 | 1,398,685 |
| Telangana | Khammam | Khammam | 2 | 1,398,685 |
| Telangana | Jogulamba Gadwal | Mahbubnagar | 4 | 1,013,257 |
| Telangana | Mahabubnagar | Mahbubnagar | 4 | 1,013,257 |
| Telangana | Nagarkurnool | Mahbubnagar | 4 | 1,013,257 |
| Telangana | Wanaparthy | Mahbubnagar | 4 | 1,013,257 |
| Telangana | Medak | Medak | 2 | 1,516,644 |
| Telangana | Siddipet | Medak | 2 | 1,516,644 |
| Telangana | Nalgonda | Nalgonda | 3 | 1,162,936 |
| Telangana | Suryapet | Nalgonda | 3 | 1,162,936 |
| Telangana | Yadadri Bhuvanagiri | Nalgonda | 3 | 1,162,936 |
| Telangana | Kamareddy | Nizamabad | 2 | 1,275,668 |
| Telangana | Nizamabad | Nizamabad | 2 | 1,275,668 |
| Telangana | Medchal-Malkajgiri | Rangareddy | 4 | 1,324,185 |
| Telangana | Ranga Reddy | Rangareddy | 4 | 1,324,185 |
| Telangana | Sangareddy | Rangareddy | 4 | 1,324,185 |
| Telangana | Vikarabad | Rangareddy | 4 | 1,324,185 |
| Telangana | Jangoan | Warangal | 5 | 702,515 |
| Telangana | Jayashankar Bhupalapally | Warangal | 5 | 702,515 |
| Telangana | Mahabubabad | Warangal | 5 | 702,515 |
| Telangana | Warangal Rural | Warangal | 5 | 702,515 |
| Telangana | Warangal Urban | Warangal | 5 | 702,515 |
| Arunachal Pradesh | Kra Daadi | Kurung Kumey | 2 | 46,038 |
| Arunachal Pradesh | Kurung Kumey | Kurung Kumey | 2 | 46,038 |
| Arunachal Pradesh | Lohit | Lohit | 2 | 72,863 |
| Arunachal Pradesh | Namsai | Lohit | 2 | 72,863 |
| Arunachal Pradesh | Longding | Tirap | 2 | 55,988 |
| Arunachal Pradesh | Tirap | Tirap | 2 | 55,988 |
| Arunachal Pradesh | Siang | West Siang | 2 | 56,137 |
| Arunachal Pradesh | West Siang | West Siang | 2 | 56,137 |
| Assam | Dhubri | Dhubri | 2 | 974,629 |
| Assam | South Salmara Mancachar | Dhubri | 2 | 974,629 |
| Assam | Jorhat | Jorhat | 2 | 546,128 |
| Assam | Majuli | Jorhat | 2 | 546,128 |
| Assam | Karbi Anglong | Karbi Anglong | 2 | 478,156 |
| Assam | West Karbi Anglong | Karbi Anglong | 2 | 478,156 |
| Assam | Hojai | Nagaon | 2 | 1,411,884 |
| Assam | Nagaon | Nagaon | 2 | 1,411,884 |
| Assam | Charaideo | Sivasagar | 2 | 575,525 |
| Assam | Sivasagar | Sivasagar | 2 | 575,525 |
| Assam | Biswanath | Sonitpur | 2 | 962,055 |
| Assam | Sonitpur | Sonitpur | 2 | 962,055 |
| Chhattisgarh | Bastar | Bastar | 2 | 706,600 |
| Chhattisgarh | Kodagaon | Bastar | 2 | 706,600 |
| Chhattisgarh | Bilaspur | Bilaspur | 2 | 1,331,814 |
| Chhattisgarh | Mungeli | Bilaspur | 2 | 1,331,814 |
| Chhattisgarh | Dantewada | Dakshin Bastar Dantewada | 2 | 266,819 |
| Chhattisgarh | Sukma | Dakshin Bastar Dantewada | 2 | 266,819 |
| Chhattisgarh | Balod | Durg | 3 | 1,114,624 |
| Chhattisgarh | Bemetara | Durg | 3 | 1,114,624 |
| Chhattisgarh | Durg | Durg | 3 | 1,114,624 |
| Chhattisgarh | Baloda Bazar | Raipur | 3 | 1,354,624 |
| Chhattisgarh | Gariyaband | Raipur | 3 | 1,354,624 |
| Chhattisgarh | Raipur | Raipur | 3 | 1,354,624 |
| Chhattisgarh | Balrampur | Surguja | 3 | 786,629 |
| Chhattisgarh | Surajpur | Surguja | 3 | 786,629 |
| Chhattisgarh | Surguja | Surguja | 3 | 786,629 |
| Gujarat | Bhavnagar | Bhavnagar | 2 | 1,440,182 |
| Gujarat | Botad | Bhavnagar | 2 | 1,440,182 |
| Gujarat | Devbhumi Dwarka | Jamnagar | 2 | 1,080,060 |
| Gujarat | Jamnagar | Jamnagar | 2 | 1,080,060 |
| Gujarat | Gir Somnath | Junagadh | 2 | 1,371,541 |
| Gujarat | Junagadh | Junagadh | 2 | 1,371,541 |
| Gujarat | Mahisagar | Panch Mahals | 2 | 1,195,388 |
| Gujarat | Panchmahal | Panch Mahals | 2 | 1,195,388 |
| Gujarat | Morbi | Rajkot | 2 | 1,902,279 |
| Gujarat | Rajkot | Rajkot | 2 | 1,902,279 |
| Gujarat | Aravali | Sabar Kantha | 2 | 1,214,294 |
| Gujarat | Sabarkantha | Sabar Kantha | 2 | 1,214,294 |
| Gujarat | Chhota Udaipur | Vadodara | 2 | 2,082,813 |
| Gujarat | Vadodara | Vadodara | 2 | 2,082,813 |
| Haryana | Bhiwani | Bhiwani | 2 | 817,222 |
| Haryana | Charkhi Dadri | Bhiwani | 2 | 817,222 |
| Madhya Pradesh | Agar Malwa | Shajapur | 2 | 756,340 |
| Madhya Pradesh | Shajapur | Shajapur | 2 | 756,340 |
| Maharashtra | Palghar | Thane | 2 | 5,530,074 |
| Maharashtra | Thane | Thane | 2 | 5,530,074 |
| Meghalaya | East Garo Hills | East Garo Hills | 2 | 158,958 |
| Meghalaya | North Garo Hills | East Garo Hills | 2 | 158,958 |
| Meghalaya | East Jantia Hills | Jaintia Hills | 2 | 197,562 |
| Meghalaya | West Jaintia Hills | Jaintia Hills | 2 | 197,562 |
| Meghalaya | South West Garo Hills | West Garo Hills | 2 | 321,646 |
| Meghalaya | West Garo Hills | West Garo Hills | 2 | 321,646 |
| Meghalaya | South West Khasi Hills | West Khasi Hills | 2 | 191,730 |
| Meghalaya | West Khasi Hills | West Khasi Hills | 2 | 191,730 |
| NCT Delhi | East | East | 2 | 854,673 |
| NCT Delhi | Shahdara | East | 2 | 854,673 |
| NCT Delhi | South | South | 2 | 1,365,964 |
| NCT Delhi | South East | South | 2 | 1,365,964 |
| Punjab | Fazilka | Firozpur | 2 | 1,014,537 |
| Punjab | Firozpur | Firozpur | 2 | 1,014,537 |
| Punjab | Gurdaspur | Gurdaspur | 2 | 1,149,162 |
| Punjab | Pathankot | Gurdaspur | 2 | 1,149,162 |
| Tripura | North Tripura | North Tripura | 2 | 346,974 |
| Tripura | Unakoti | North Tripura | 2 | 346,974 |
| Tripura | Gomati | South Tripura | 2 | 438,000 |
| Tripura | South Tripura | South Tripura | 2 | 438,000 |
| Tripura | Khowai | West Tripura | 3 | 575,246 |
| Tripura | Sepahijala | West Tripura | 3 | 575,246 |
| Tripura | West Tripura | West Tripura | 3 | 575,246 |
| Uttar Pradesh | Ghaziabad | Ghaziabad | 2 | 2,340,822 |
| Uttar Pradesh | Hapur | Ghaziabad | 2 | 2,340,822 |
| Uttar Pradesh | Moradabad | Moradabad | 2 | 2,386,003 |
| Uttar Pradesh | Sambhal | Moradabad | 2 | 2,386,003 |
| Uttar Pradesh | Muzaffarnagar | Muzaffarnagar | 2 | 2,071,756 |
| Uttar Pradesh | Shamli | Muzaffarnagar | 2 | 2,071,756 |
| Uttar Pradesh | Amethi | Sultanpur | 2 | 1,898,558 |
| Uttar Pradesh | Sultanpur | Sultanpur | 2 | 1,898,558 |
| West Bengal | Paschim Barddhaman | Barddhaman | 2 | 3,858,782 |
| West Bengal | Purba Barddhaman | Barddhaman | 2 | 3,858,782 |

## Unmatched districts

No Census 2011 counterpart scored above threshold. These carry no population denominator and are therefore excluded from the allocation. Each is a candidate for a `child_of` row in `config/district_overrides.csv`.

_None._

## Low-confidence matches (accepted, flagged)

Scored between 80 and 90. Accepted, but these are the rows to read manually before trusting the result.

| NFHS district | Census district | Score |
|---|---|---|
| Bihar / Buxer | BIHAR / Buxar | 80 |
| West Bengal / Darjeeling | WEST BENGAL / Darjiling | 84 |
| Gujarat / Ahmedabad | GUJARAT / Ahmadabad | 89 |
