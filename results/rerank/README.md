# Rerank runs

| run | model | prompt | samples | order | candidates shown | bugs | sample status | cost (USD) | in / out tokens | stability (mean tau) | grounded top-3 |
| --- | --- | --- | ---: | --- | --- | ---: | --- | ---: | --- | --- | ---: |
| `haiku-v1-s5` | claude-haiku-5-5 (low) | v1 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.0104 | 65810 / 7559 | 1.00 | 0.07 |
| `haiku-v1-s5-allcand` | claude-haiku-5-5 (low) | v1 | 5 | shuffle | all | 3 | ok | 0.0194 | 156155 / 7579 | 0.44 | 0.02 |
| `haiku-v1-s5-sbforder` | claude-haiku-5-5 (low) | v1 | 5 | sbfl | Ochiai > 0 | 3 | ok | 0.0101 | 65810 / 6984 | 1.00 | 0.05 |
| `haiku-v2-s5-batch` | claude-haiku-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.0053 | 67385 / 7800 | 1.00 | 1.00 |
| `opus-v1-s1-sbforder` | claude-opus-5-5 (low) | v1 | 1 | sbfl | Ochiai > 0 | 3 | ok | 0.0651 | 13162 / 623 | - | 0.00 |
| `opus-v1-s5` | claude-opus-5-5 (low) | v1 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.3240 | 65810 / 3037 | 1.00 | 0.00 |
| `opus-v1-s5-allcand` | claude-opus-5-5 (low) | v1 | 5 | shuffle | all | 3 | ok | 0.6994 | 156155 / 3739 | 0.47 | 0.00 |
| `opus-v2-s5` | claude-opus-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.3319 | 67385 / 3116 | 1.00 | 1.00 |
| `opus-v2-s5-adaptive` | claude-opus-5-5 (low) | v2 | 5 | shuffle | Ochiai > 0 | 3 | ok | 0.2840 | 58753 / 2448 | 1.00 | 1.00 |

Top-1 per configuration (no correctness claim; C owns labels):

| run | bug | SBFL | single | mean | fused w=0.5 (mean) |
| --- | --- | --- | --- | --- | --- |
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
| `opus-v2-s5` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |
| `opus-v2-s5-adaptive` | Lang-1 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5-adaptive` | Lang-3 | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber | NumberUtils#createNumber |
| `opus-v2-s5-adaptive` | Lang-4 | LookupTranslator#translate | LookupTranslator#<init> | LookupTranslator#<init> | LookupTranslator#translate |

Output contract: [docs/person_b_output_contract.md](../../docs/person_b_output_contract.md)
