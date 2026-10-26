# Rerank runs

Roles: `main` = frozen midterm configuration (Opus, prompt v2, all 20 candidates, 5 shuffled samples, direct calls, fusion w=0.5); `extra-haiku` and `secondary-nonzero` are the labeled additional configurations; `dev-exploration` runs are pilot history on the dev bugs, not formal results.

| role | run | model | prompt | samples | order | candidates shown | bugs | sample status | cost (USD) | in / out tokens | stability (mean tau) | grounded top-3 |
| --- | --- | --- | --- | ---: | --- | --- | ---: | --- | ---: | --- | --- | ---: |
| main | `langexp1023-opus-v2-k20-s5` | claude-opus-5-5 (low) | v2 | 5 | shuffle | all | 10 | ok | 2.1257 | 465355 / 13215 | 0.69 | 0.99 |
| main | `opus-v2-k20-s5` | claude-opus-5-5 (low) | v2 | 5 | shuffle | all | 3 | ok | 0.7133 | 157325 / 4198 | 0.38 | 1.00 |
| extra-haiku | `haiku-v2-k20-s5` | claude-haiku-5-5 (low) | v2 | 5 | shuffle | all | 3 | ok | 0.0198 | 157325 / 8214 | 0.37 | 1.00 |
| extra-haiku | `langexp1023-haiku-v2-k20-s5` | claude-haiku-5-5 (low) | v2 | 5 | shuffle | all | 10 | ok | 0.0615 | 474907 / 27946 | 0.64 | 0.98 |
| secondary-nonzero | `langexp1023-opus-v2-nz-s5` | claude-opus-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 10 | ok | 1.4900 | 315520 / 11398 | 0.92 | 0.99 |
| secondary-nonzero | `opus-v2-s5` | claude-opus-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.3319 | 67385 / 3116 | 1.00 | 1.00 |
| dev-exploration | `haiku-v1-s5` | claude-haiku-5-5 (low) | v1 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.0104 | 65810 / 7559 | 1.00 | 0.07 |
| dev-exploration | `haiku-v1-s5-allcand` | claude-haiku-5-5 (low) | v1 | 5 | shuffle | all | 3 | ok | 0.0194 | 156155 / 7579 | 0.44 | 0.02 |
| dev-exploration | `haiku-v1-s5-sbforder` | claude-haiku-5-5 (low) | v1 | 5 | sbfl | Ochiai > 0 | 3 | ok | 0.0101 | 65810 / 6984 | 1.00 | 0.05 |
| dev-exploration | `haiku-v2-s5-batch` | claude-haiku-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.0053 | 67385 / 7800 | 1.00 | 1.00 |
| dev-exploration | `opus-v1-s1-sbforder` | claude-opus-5-5 (low) | v1 | 1 | sbfl | Ochiai > 0 | 3 | ok | 0.0651 | 13162 / 623 | - | 0.00 |
| dev-exploration | `opus-v1-s5` | claude-opus-5-5 (low) | v1 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.3240 | 65810 / 3037 | 1.00 | 0.00 |
| dev-exploration | `opus-v1-s5-allcand` | claude-opus-5-5 (low) | v1 | 5 | shuffle | all | 3 | ok | 0.6994 | 156155 / 3739 | 0.47 | 0.00 |
| dev-exploration | `opus-v2-s5-adaptive` | claude-opus-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.2840 | 58753 / 2448 | 1.00 | 1.00 |

Top-1 per configuration (no correctness claim; C owns labels):

| run | bug | SBFL | single | mean | fused w=0.5 (mean) |
| --- | --- | --- | --- | --- | --- |
| `langexp1023-opus-v2-k20-s5` | Lang-5 | LocaleUtils#toLocale | LocaleUtils#toLocale | LocaleUtils#toLocale | LocaleUtils#toLocale |
| `langexp1023-opus-v2-k20-s5` | Lang-6 | StringEscapeUtils#escapeCsv | StringEscapeUtils$CsvEscaper#translate | StringEscapeUtils$CsvEscaper#translate | StringEscapeUtils#escapeCsv |
| `langexp1023-opus-v2-k20-s5` | Lang-7 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `langexp1023-opus-v2-k20-s5` | Lang-8 | FastDateParser$TextStrategy#isNumber | FastDatePrinter$TimeZoneNameRule#appendTo | FastDatePrinter$TimeZoneNameRule#appendTo | FastDatePrinter$TimeZoneNameRule#appendTo |
| `langexp1023-opus-v2-k20-s5` | Lang-9 | FastDateParser#getParsePattern | FastDateParser#init | FastDateParser#init | FastDateParser#parse |
| `langexp1023-opus-v2-k20-s5` | Lang-10 | FastDateParser#getParsePattern | FastDateParser#escapeRegex | FastDateParser#escapeRegex | FastDateParser$TextStrategy#setCalendar |
| `langexp1023-opus-v2-k20-s5` | Lang-11 | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random |
| `langexp1023-opus-v2-k20-s5` | Lang-12 | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random |
| `langexp1023-opus-v2-k20-s5` | Lang-13 | SerializationUtils#clone | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass |
| `langexp1023-opus-v2-k20-s5` | Lang-14 | StringUtils#equals | StringUtils#equals | StringUtils#equals | StringUtils#equals |
| `opus-v2-k20-s5` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-k20-s5` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-k20-s5` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `haiku-v2-k20-s5` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v2-k20-s5` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v2-k20-s5` | Lang-4 | LookupTranslator#translate | LookupTranslator#translate | LookupTranslator#translate | LookupTranslator#translate |
| `langexp1023-haiku-v2-k20-s5` | Lang-5 | LocaleUtils#toLocale | LocaleUtils#toLocale | LocaleUtils#toLocale | LocaleUtils#toLocale |
| `langexp1023-haiku-v2-k20-s5` | Lang-6 | StringEscapeUtils#escapeCsv | StringEscapeUtils$CsvEscaper#translate | StringEscapeUtils$CsvEscaper#translate | StringEscapeUtils$CsvEscaper#translate |
| `langexp1023-haiku-v2-k20-s5` | Lang-7 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `langexp1023-haiku-v2-k20-s5` | Lang-8 | FastDateParser$TextStrategy#isNumber | FastDatePrinter$TimeZoneNameRule#appendTo | FastDatePrinter$TimeZoneNameRule#appendTo | FastDatePrinter$TimeZoneNameRule#appendTo |
| `langexp1023-haiku-v2-k20-s5` | Lang-9 | FastDateParser#getParsePattern | FastDateParser#escapeRegex | FastDateParser#escapeRegex | FastDateParser#getStrategy |
| `langexp1023-haiku-v2-k20-s5` | Lang-10 | FastDateParser#getParsePattern | FastDateParser$TextStrategy#addRegex | FastDateParser#escapeRegex | FastDateParser$TextStrategy#setCalendar |
| `langexp1023-haiku-v2-k20-s5` | Lang-11 | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random |
| `langexp1023-haiku-v2-k20-s5` | Lang-12 | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random |
| `langexp1023-haiku-v2-k20-s5` | Lang-13 | SerializationUtils#clone | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass |
| `langexp1023-haiku-v2-k20-s5` | Lang-14 | StringUtils#equals | StringUtils#equals | StringUtils#equals | StringUtils#equals |
| `langexp1023-opus-v2-nz-s5` | Lang-5 | LocaleUtils#toLocale | LocaleUtils#toLocale | LocaleUtils#toLocale | LocaleUtils#toLocale |
| `langexp1023-opus-v2-nz-s5` | Lang-6 | StringEscapeUtils#escapeCsv | StringEscapeUtils$CsvEscaper#translate | StringEscapeUtils$CsvEscaper#translate | StringEscapeUtils#escapeCsv |
| `langexp1023-opus-v2-nz-s5` | Lang-7 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `langexp1023-opus-v2-nz-s5` | Lang-8 | FastDateParser$TextStrategy#isNumber | FastDatePrinter$TimeZoneNameRule#appendTo | FastDatePrinter$TimeZoneNameRule#appendTo | FastDatePrinter$TimeZoneNameRule#appendTo |
| `langexp1023-opus-v2-nz-s5` | Lang-9 | FastDateParser#getParsePattern | FastDateParser#init | FastDateParser#init | FastDateParser#parse |
| `langexp1023-opus-v2-nz-s5` | Lang-10 | FastDateParser#getParsePattern | FastDateParser#escapeRegex | FastDateParser#escapeRegex | FastDateParser$TextStrategy#setCalendar |
| `langexp1023-opus-v2-nz-s5` | Lang-11 | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random |
| `langexp1023-opus-v2-nz-s5` | Lang-12 | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random | RandomStringUtils#random |
| `langexp1023-opus-v2-nz-s5` | Lang-13 | SerializationUtils#clone | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass | SerializationUtils$ClassLoaderAwareObjectInputStream#resolveClass |
| `langexp1023-opus-v2-nz-s5` | Lang-14 | StringUtils#equals | StringUtils#equals | StringUtils#equals | StringUtils#equals |
| `opus-v2-s5` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `haiku-v1-s5` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v1-s5` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v1-s5` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `haiku-v1-s5-allcand` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v1-s5-allcand` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v1-s5-allcand` | Lang-4 | LookupTranslator#translate | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#translate |
| `haiku-v1-s5-sbforder` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v1-s5-sbforder` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v1-s5-sbforder` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `haiku-v2-s5-batch` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v2-s5-batch` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `haiku-v2-s5-batch` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `opus-v1-s1-sbforder` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v1-s1-sbforder` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v1-s1-sbforder` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `opus-v1-s5` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v1-s5` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v1-s5` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `opus-v1-s5-allcand` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v1-s5-allcand` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v1-s5-allcand` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `opus-v2-s5-adaptive` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5-adaptive` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5-adaptive` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |

Output contract: [docs/person_b_output_contract.md](../../docs/person_b_output_contract.md)
