// @ts-nocheck
import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Select,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  useCanvasState,
} from "cursor/canvas";

const DATA: any = {
  "upload": [
    {
      "company": "Clearsulting",
      "files": 28,
      "mb": 37.2,
      "folders": 9
    },
    {
      "company": "Elder Care",
      "files": 1386,
      "mb": 1822.8,
      "folders": 160
    },
    {
      "company": "GKF",
      "files": 42,
      "mb": 22.6,
      "folders": 18
    },
    {
      "company": "SPG",
      "files": 511,
      "mb": 866.6,
      "folders": 62
    }
  ],
  "chunks": [
    {
      "company": "Clearsulting",
      "chunks": 2237,
      "files": 21,
      "chars": 4016608,
      "words": 1028511,
      "tokens4": 1004152,
      "avg_chars": 1795.5,
      "p50": 294,
      "p95": 7374
    },
    {
      "company": "Elder Care",
      "chunks": 35104,
      "files": 218,
      "chars": 179229685,
      "words": 31813515,
      "tokens4": 44807421,
      "avg_chars": 5105.7,
      "p50": 6637,
      "p95": 7466
    },
    {
      "company": "GKF",
      "chunks": 3038,
      "files": 40,
      "chars": 11810864,
      "words": 2072952,
      "tokens4": 2952716,
      "avg_chars": 3887.7,
      "p50": 3704,
      "p95": 7381
    },
    {
      "company": "SPG",
      "chunks": 71010,
      "files": 355,
      "chars": 372380130,
      "words": 58036177,
      "tokens4": 93095032,
      "avg_chars": 5244.1,
      "p50": 6864,
      "p95": 7440
    }
  ],
  "join": [
    {
      "company": "Clearsulting",
      "should_parse": 22,
      "ingested": 21,
      "missing": 1,
      "pct": 95.5
    },
    {
      "company": "Elder Care",
      "should_parse": 379,
      "ingested": 197,
      "missing": 182,
      "pct": 52.0
    },
    {
      "company": "GKF",
      "should_parse": 40,
      "ingested": 40,
      "missing": 0,
      "pct": 100.0
    },
    {
      "company": "SPG",
      "should_parse": 364,
      "ingested": 323,
      "missing": 41,
      "pct": 88.7
    }
  ],
  "formats": {
    "Clearsulting": {
      "xlsx": 17,
      "pdf": 10,
      "docx": 1
    },
    "Elder Care": {
      "pdf": 1099,
      "xlsx": 208,
      "docx": 76,
      "other": 3
    },
    "GKF": {
      "xlsx": 34,
      "pdf": 8
    },
    "SPG": {
      "pdf": 411,
      "xlsx": 100
    }
  },
  "source_types": {
    "Clearsulting": {
      "vision": {
        "chunks": 1093,
        "chars": 290229,
        "words": 40575
      },
      "text": {
        "chunks": 1054,
        "chars": 3605412,
        "words": 960688
      },
      "table": {
        "chunks": 90,
        "chars": 120967,
        "words": 27248
      }
    },
    "Elder Care": {
      "text": {
        "chunks": 32273,
        "chars": 177357094,
        "words": 31460757
      },
      "table": {
        "chunks": 1490,
        "chars": 1358260,
        "words": 267024
      },
      "vision": {
        "chunks": 1341,
        "chars": 514331,
        "words": 85734
      }
    },
    "GKF": {
      "text": {
        "chunks": 2403,
        "chars": 11420448,
        "words": 2002987
      },
      "table": {
        "chunks": 322,
        "chars": 280350,
        "words": 52980
      },
      "vision": {
        "chunks": 313,
        "chars": 110066,
        "words": 16985
      }
    }
  },
  "file_types": {
    "Clearsulting": {
      "pdf": {
        "chunks": 1620,
        "files": 6,
        "chars": 679430
      },
      "xlsx": {
        "chunks": 617,
        "files": 15,
        "chars": 3337178
      }
    },
    "Elder Care": {
      "xlsx": {
        "chunks": 30570,
        "files": 105,
        "chars": 174576398
      },
      "pdf": {
        "chunks": 4278,
        "files": 97,
        "chars": 3895858
      },
      "csv": {
        "chunks": 136,
        "files": 3,
        "chars": 641931
      },
      "docx": {
        "chunks": 120,
        "files": 13,
        "chars": 115498
      }
    },
    "GKF": {
      "xlsx": {
        "chunks": 1801,
        "files": 33,
        "chars": 10135454
      },
      "pdf": {
        "chunks": 1237,
        "files": 7,
        "chars": 1675410
      }
    }
  },
  "confidence": {
    "Clearsulting": {
      "medium": 16,
      "low": 6,
      "high": 6
    },
    "Elder Care": {
      "low": 880,
      "medium": 322,
      "high": 184
    },
    "GKF": {
      "medium": 32,
      "high": 9,
      "low": 1
    },
    "SPG": {
      "medium": 315,
      "low": 151,
      "high": 45
    }
  },
  "priority": {
    "Clearsulting": {
      "None": 6,
      "1": 6,
      "2": 12,
      "3": 4
    },
    "Elder Care": {
      "None": 987,
      "1": 27,
      "2": 179,
      "3": 193
    },
    "GKF": {
      "None": 1,
      "1": 6,
      "2": 19,
      "3": 16
    },
    "SPG": {
      "None": 117,
      "1": 33,
      "2": 184,
      "3": 177
    }
  },
  "workstreams": {
    "Clearsulting": [
      {
        "ws": "FINANCIAL",
        "docs": 12,
        "should_parse": 12,
        "high": 4,
        "med": 8,
        "low": 0,
        "avg_tier": 1.67
      },
      {
        "ws": "BACKGROUND",
        "docs": 6,
        "should_parse": 0,
        "high": 0,
        "med": 0,
        "low": 6,
        "avg_tier": 0.0
      },
      {
        "ws": "BUSINESS_MODEL",
        "docs": 5,
        "should_parse": 5,
        "high": 1,
        "med": 4,
        "low": 0,
        "avg_tier": 1.8
      },
      {
        "ws": "KPI_OPS",
        "docs": 5,
        "should_parse": 5,
        "high": 1,
        "med": 4,
        "low": 0,
        "avg_tier": 2.6
      },
      {
        "ws": "CUSTOMER",
        "docs": 2,
        "should_parse": 2,
        "high": 0,
        "med": 2,
        "low": 0,
        "avg_tier": 2.0
      },
      {
        "ws": "FORECAST",
        "docs": 1,
        "should_parse": 1,
        "high": 1,
        "med": 0,
        "low": 0,
        "avg_tier": 1.0
      },
      {
        "ws": "QUALITY_EARNINGS",
        "docs": 1,
        "should_parse": 1,
        "high": 1,
        "med": 0,
        "low": 0,
        "avg_tier": 1.0
      }
    ],
    "Elder Care": [
      {
        "ws": "BACKGROUND",
        "docs": 621,
        "should_parse": 6,
        "high": 124,
        "med": 6,
        "low": 491,
        "avg_tier": 3.0
      },
      {
        "ws": "FINANCIAL",
        "docs": 582,
        "should_parse": 210,
        "high": 43,
        "med": 154,
        "low": 385,
        "avg_tier": 2.5
      },
      {
        "ws": "LEGAL",
        "docs": 114,
        "should_parse": 113,
        "high": 4,
        "med": 107,
        "low": 3,
        "avg_tier": 2.28
      },
      {
        "ws": "KPI_OPS",
        "docs": 36,
        "should_parse": 36,
        "high": 5,
        "med": 30,
        "low": 1,
        "avg_tier": 2.64
      },
      {
        "ws": "BUSINESS_MODEL",
        "docs": 26,
        "should_parse": 26,
        "high": 1,
        "med": 25,
        "low": 0,
        "avg_tier": 1.96
      },
      {
        "ws": "CUSTOMER",
        "docs": 9,
        "should_parse": 9,
        "high": 8,
        "med": 1,
        "low": 0,
        "avg_tier": 2.0
      },
      {
        "ws": "QUALITY_EARNINGS",
        "docs": 8,
        "should_parse": 8,
        "high": 8,
        "med": 0,
        "low": 0,
        "avg_tier": 2.0
      },
      {
        "ws": "FORECAST",
        "docs": 3,
        "should_parse": 3,
        "high": 3,
        "med": 0,
        "low": 0,
        "avg_tier": 1.0
      }
    ],
    "GKF": [
      {
        "ws": "FINANCIAL",
        "docs": 33,
        "should_parse": 33,
        "high": 5,
        "med": 28,
        "low": 0,
        "avg_tier": 2.27
      },
      {
        "ws": "BUSINESS_MODEL",
        "docs": 5,
        "should_parse": 5,
        "high": 4,
        "med": 1,
        "low": 0,
        "avg_tier": 1.6
      },
      {
        "ws": "LEGAL",
        "docs": 4,
        "should_parse": 4,
        "high": 1,
        "med": 3,
        "low": 0,
        "avg_tier": 2.5
      },
      {
        "ws": "QUALITY_EARNINGS",
        "docs": 2,
        "should_parse": 2,
        "high": 2,
        "med": 0,
        "low": 0,
        "avg_tier": 1.0
      },
      {
        "ws": "BACKGROUND",
        "docs": 1,
        "should_parse": 0,
        "high": 0,
        "med": 0,
        "low": 1,
        "avg_tier": 0.0
      },
      {
        "ws": "CUSTOMER",
        "docs": 1,
        "should_parse": 1,
        "high": 0,
        "med": 1,
        "low": 0,
        "avg_tier": 2.0
      },
      {
        "ws": "KPI_OPS",
        "docs": 1,
        "should_parse": 1,
        "high": 0,
        "med": 1,
        "low": 0,
        "avg_tier": 2.0
      },
      {
        "ws": "FORECAST",
        "docs": 1,
        "should_parse": 1,
        "high": 1,
        "med": 0,
        "low": 0,
        "avg_tier": 1.0
      }
    ],
    "SPG": [
      {
        "ws": "LEGAL",
        "docs": 191,
        "should_parse": 191,
        "high": 0,
        "med": 190,
        "low": 1,
        "avg_tier": 2.28
      },
      {
        "ws": "FINANCIAL",
        "docs": 158,
        "should_parse": 155,
        "high": 40,
        "med": 114,
        "low": 4,
        "avg_tier": 2.32
      },
      {
        "ws": "BACKGROUND",
        "docs": 132,
        "should_parse": 16,
        "high": 0,
        "med": 0,
        "low": 132,
        "avg_tier": 3.0
      },
      {
        "ws": "KPI_OPS",
        "docs": 27,
        "should_parse": 24,
        "high": 5,
        "med": 8,
        "low": 14,
        "avg_tier": 2.81
      },
      {
        "ws": "QUALITY_EARNINGS",
        "docs": 16,
        "should_parse": 16,
        "high": 7,
        "med": 6,
        "low": 3,
        "avg_tier": 1.56
      },
      {
        "ws": "BUSINESS_MODEL",
        "docs": 3,
        "should_parse": 3,
        "high": 0,
        "med": 3,
        "low": 0,
        "avg_tier": 2.67
      },
      {
        "ws": "FORECAST",
        "docs": 1,
        "should_parse": 1,
        "high": 1,
        "med": 0,
        "low": 0,
        "avg_tier": 1.0
      }
    ]
  },
  "emb_ws_text": {
    "Clearsulting": [
      {
        "ws": "FINANCIAL",
        "embeddings": 590,
        "chars": 2437382,
        "words": 559137,
        "avg_chars": 4131.2
      },
      {
        "ws": "KPI_OPS",
        "embeddings": 179,
        "chars": 1090017,
        "words": 401987,
        "avg_chars": 6089.5
      },
      {
        "ws": "BUSINESS_MODEL",
        "embeddings": 1468,
        "chars": 489209,
        "words": 67387,
        "avg_chars": 333.2
      },
      {
        "ws": "CUSTOMER",
        "embeddings": 62,
        "chars": 264092,
        "words": 32551,
        "avg_chars": 4259.5
      },
      {
        "ws": "QUALITY_EARNINGS",
        "embeddings": 149,
        "chars": 187918,
        "words": 36970,
        "avg_chars": 1261.2
      },
      {
        "ws": "FORECAST",
        "embeddings": 4,
        "chars": 14138,
        "words": 1846,
        "avg_chars": 3534.5
      }
    ],
    "Elder Care": [
      {
        "ws": "FINANCIAL",
        "embeddings": 23848,
        "chars": 119306957,
        "words": 19165722,
        "avg_chars": 5002.8
      },
      {
        "ws": "KPI_OPS",
        "embeddings": 8710,
        "chars": 54468734,
        "words": 11745157,
        "avg_chars": 6253.6
      },
      {
        "ws": "QUALITY_EARNINGS",
        "embeddings": 5472,
        "chars": 30119639,
        "words": 4673822,
        "avg_chars": 5504.3
      },
      {
        "ws": "FORECAST",
        "embeddings": 1341,
        "chars": 6410916,
        "words": 792839,
        "avg_chars": 4780.7
      },
      {
        "ws": "BUSINESS_MODEL",
        "embeddings": 1198,
        "chars": 3187722,
        "words": 548852,
        "avg_chars": 2660.9
      },
      {
        "ws": "LEGAL",
        "embeddings": 1350,
        "chars": 2028716,
        "words": 320409,
        "avg_chars": 1502.8
      },
      {
        "ws": "CUSTOMER",
        "embeddings": 89,
        "chars": 489297,
        "words": 83782,
        "avg_chars": 5497.7
      }
    ],
    "GKF": [
      {
        "ws": "FINANCIAL",
        "embeddings": 1800,
        "chars": 10132765,
        "words": 1804099,
        "avg_chars": 5629.3
      },
      {
        "ws": "QUALITY_EARNINGS",
        "embeddings": 1184,
        "chars": 7796824,
        "words": 1484634,
        "avg_chars": 6585.2
      },
      {
        "ws": "LEGAL",
        "embeddings": 754,
        "chars": 1453637,
        "words": 233731,
        "avg_chars": 1927.9
      },
      {
        "ws": "FORECAST",
        "embeddings": 230,
        "chars": 1016816,
        "words": 115864,
        "avg_chars": 4420.9
      },
      {
        "ws": "BUSINESS_MODEL",
        "embeddings": 597,
        "chars": 681143,
        "words": 119849,
        "avg_chars": 1140.9
      },
      {
        "ws": "CUSTOMER",
        "embeddings": 1,
        "chars": 2689,
        "words": 544,
        "avg_chars": 2689.0
      },
      {
        "ws": "KPI_OPS",
        "embeddings": 1,
        "chars": 2689,
        "words": 544,
        "avg_chars": 2689.0
      }
    ]
  },
  "profiles": [
    {
      "company_name": "Clearsulting",
      "industry_overlay": "healthcare_services",
      "overlay_confidence": "high",
      "deal_type": "recapitalization",
      "banked": "true",
      "n_gaps": "1",
      "desc_chars": "434"
    },
    {
      "company_name": "Elder Care",
      "industry_overlay": "healthcare_services",
      "overlay_confidence": "high",
      "deal_type": "buyout",
      "banked": "true",
      "n_gaps": "1",
      "desc_chars": "325"
    },
    {
      "company_name": "GKF",
      "industry_overlay": "healthcare_services",
      "overlay_confidence": "medium",
      "deal_type": "unknown",
      "banked": "true",
      "n_gaps": "6",
      "desc_chars": "348"
    },
    {
      "company_name": "SPG",
      "industry_overlay": "other",
      "overlay_confidence": "low",
      "deal_type": "unknown",
      "banked": "false",
      "n_gaps": "7",
      "desc_chars": "111"
    }
  ],
  "agents": {
    "Clearsulting": {
      "BMA": {
        "gaps": 6,
        "exec": 0,
        "citations": 2,
        "extra": {
          "cim": "true",
          "flag": "Red",
          "conf": "medium"
        }
      },
      "FTA": {
        "gaps": 1,
        "exec": 490,
        "citations": 2,
        "extra": {
          "addback_pct": "45.7"
        }
      },
      "Legal": {
        "gaps": 11,
        "exec": 264,
        "citations": 2,
        "extra": {
          "section_conf": "low",
          "contract_chars": 2
        }
      },
      "CQA": {
        "gaps": 3,
        "exec": 773,
        "citations": 5571,
        "extra": {}
      },
      "KPI": {
        "gaps": 10,
        "exec": 829,
        "citations": 3320,
        "extra": {
          "overlay": "tech_services",
          "missing_chars": 3761
        }
      },
      "QoE": {
        "gaps": 0,
        "exec": 841,
        "citations": 4934,
        "extra": {
          "qofe": "true",
          "tier4": "9"
        }
      }
    },
    "Elder Care": {
      "BMA": {
        "gaps": 7,
        "exec": 0,
        "citations": 2,
        "extra": {
          "cim": "true",
          "flag": "Yellow",
          "conf": "high"
        }
      },
      "FTA": {
        "gaps": 1,
        "exec": 428,
        "citations": 2,
        "extra": {
          "addback_pct": "246.9"
        }
      },
      "Legal": {
        "gaps": 5,
        "exec": 221,
        "citations": 6942,
        "extra": {
          "section_conf": "high",
          "contract_chars": 3825
        }
      },
      "CQA": {
        "gaps": 0,
        "exec": 738,
        "citations": 1668,
        "extra": {}
      },
      "KPI": {
        "gaps": 9,
        "exec": 719,
        "citations": 4377,
        "extra": {
          "overlay": "healthcare_services",
          "missing_chars": 3593
        }
      },
      "QoE": {
        "gaps": 1,
        "exec": 908,
        "citations": 3063,
        "extra": {
          "qofe": "false",
          "tier4": "17"
        }
      }
    },
    "GKF": {
      "BMA": {
        "gaps": 4,
        "exec": 0,
        "citations": 3981,
        "extra": {
          "cim": "false",
          "flag": "Yellow",
          "conf": "medium"
        }
      },
      "FTA": {
        "gaps": 5,
        "exec": 613,
        "citations": 2,
        "extra": {
          "addback_pct": null
        }
      },
      "Legal": {
        "gaps": 5,
        "exec": 239,
        "citations": 3165,
        "extra": {
          "section_conf": "high",
          "contract_chars": 1300
        }
      },
      "CQA": {
        "gaps": 1,
        "exec": 774,
        "citations": 1996,
        "extra": {}
      },
      "KPI": {
        "gaps": 9,
        "exec": 827,
        "citations": 5288,
        "extra": {
          "overlay": "healthcare_services",
          "missing_chars": 3865
        }
      },
      "QoE": {
        "gaps": 1,
        "exec": 996,
        "citations": 6368,
        "extra": {
          "qofe": "true",
          "tier4": "3"
        }
      }
    },
    "SPG": {
      "BMA": {
        "gaps": 4,
        "exec": 0,
        "citations": 2,
        "extra": {
          "cim": "false",
          "flag": "Yellow",
          "conf": "medium"
        }
      },
      "FTA": {
        "gaps": 2,
        "exec": 334,
        "citations": 2,
        "extra": {
          "addback_pct": null
        }
      },
      "Legal": {
        "gaps": 11,
        "exec": 264,
        "citations": 317,
        "extra": {
          "section_conf": "low",
          "contract_chars": "2"
        }
      },
      "CQA": {
        "gaps": 0,
        "exec": 608,
        "citations": 1249,
        "extra": {}
      },
      "KPI": {
        "gaps": 10,
        "exec": 648,
        "citations": 1686,
        "extra": {
          "overlay": "healthcare_services",
          "missing_chars": "4094"
        }
      },
      "QoE": {
        "gaps": 2,
        "exec": 1095,
        "citations": 2365,
        "extra": {
          "qofe": "false",
          "tier4": "0"
        }
      }
    }
  },
  "intent_rollup": [
    {
      "agent": "bma",
      "intents": 9,
      "avg_recall": 0.01,
      "avg_mrr": 1.0,
      "avg_results": 11.8,
      "empty_n": 0
    },
    {
      "agent": "cqa",
      "intents": 5,
      "avg_recall": 0.0,
      "avg_mrr": 0.0,
      "avg_results": 1.6,
      "empty_n": 3
    },
    {
      "agent": "fta.ebitda",
      "intents": 4,
      "avg_recall": 0.051,
      "avg_mrr": 0.083,
      "avg_results": 7.0,
      "empty_n": 0
    },
    {
      "agent": "fta.opex",
      "intents": 3,
      "avg_recall": 0.192,
      "avg_mrr": 0.5,
      "avg_results": 6.7,
      "empty_n": 0
    },
    {
      "agent": "fta.revenue",
      "intents": 6,
      "avg_recall": 0.092,
      "avg_mrr": 0.2,
      "avg_results": 6.2,
      "empty_n": 0
    },
    {
      "agent": "kpi",
      "intents": 5,
      "avg_recall": 0.029,
      "avg_mrr": 0.867,
      "avg_results": 6.6,
      "empty_n": 0
    },
    {
      "agent": "legal",
      "intents": 5,
      "avg_recall": 0.129,
      "avg_mrr": 0.6,
      "avg_results": 8.2,
      "empty_n": 0
    },
    {
      "agent": "profiler",
      "intents": 7,
      "avg_recall": 0.006,
      "avg_mrr": 0.857,
      "avg_results": 4.3,
      "empty_n": 1
    },
    {
      "agent": "qoe",
      "intents": 5,
      "avg_recall": 0.002,
      "avg_mrr": 1.0,
      "avg_results": 6.0,
      "empty_n": 1
    }
  ],
  "intents": [
    {
      "agent": "bma",
      "intent": "bma.detect_cim_presence",
      "status": "evaluated",
      "recall": 0.006,
      "mrr": 1.0,
      "n": 3,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_business_overview",
      "status": "evaluated",
      "recall": 0.0199,
      "mrr": 1.0,
      "n": 11,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_model_changes_and_dependencies",
      "status": "evaluated",
      "recall": 0.0183,
      "mrr": 1.0,
      "n": 18,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_people_and_org",
      "status": "evaluated",
      "recall": 0.0199,
      "mrr": 1.0,
      "n": 15,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_pricing_and_margins",
      "status": "evaluated",
      "recall": 0.0016,
      "mrr": 1.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_revenue_by_location_and_metrics",
      "status": "evaluated",
      "recall": 0.0026,
      "mrr": 1.0,
      "n": 15,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_revenue_visibility",
      "status": "evaluated",
      "recall": 0.0026,
      "mrr": 1.0,
      "n": 12,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_sales_and_customers",
      "status": "evaluated",
      "recall": 0.0183,
      "mrr": 1.0,
      "n": 11,
      "mode": "semantic"
    },
    {
      "agent": "bma",
      "intent": "bma.retrieve_workforce_and_capacity",
      "status": "evaluated",
      "recall": 0.0026,
      "mrr": 1.0,
      "n": 15,
      "mode": "semantic"
    },
    {
      "agent": "cqa",
      "intent": "cqa.retrieve_account_size",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 0,
      "mode": "empty"
    },
    {
      "agent": "cqa",
      "intent": "cqa.retrieve_customer_concentration",
      "status": "skipped_bootstrap_failed",
      "recall": null,
      "mrr": null,
      "n": 0,
      "mode": null
    },
    {
      "agent": "cqa",
      "intent": "cqa.retrieve_customer_tenure",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 0,
      "mode": "empty"
    },
    {
      "agent": "cqa",
      "intent": "cqa.retrieve_payor_mix",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "cqa",
      "intent": "cqa.retrieve_retention_metrics",
      "status": "skipped_bootstrap_failed",
      "recall": null,
      "mrr": null,
      "n": 2,
      "mode": null
    },
    {
      "agent": "fta.ebitda",
      "intent": "fta.ebitda.q1_financial_statements",
      "status": "skipped_bootstrap_failed",
      "recall": null,
      "mrr": null,
      "n": 10,
      "mode": null
    },
    {
      "agent": "fta.ebitda",
      "intent": "fta.ebitda.q2_ebitda_and_margins",
      "status": "evaluated",
      "recall": 0.1538,
      "mrr": 0.25,
      "n": 8,
      "mode": "semantic"
    },
    {
      "agent": "fta.ebitda",
      "intent": "fta.ebitda.q3_working_capital",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 4,
      "mode": "semantic"
    },
    {
      "agent": "fta.ebitda",
      "intent": "fta.ebitda.q4_addback_schedule",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "fta.opex",
      "intent": "fta.opex.q1_financial_statements",
      "status": "skipped_bootstrap_failed",
      "recall": null,
      "mrr": null,
      "n": 8,
      "mode": null
    },
    {
      "agent": "fta.opex",
      "intent": "fta.opex.q2_working_capital",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 4,
      "mode": "semantic"
    },
    {
      "agent": "fta.opex",
      "intent": "fta.opex.q3_projected_financials",
      "status": "evaluated",
      "recall": 0.3846,
      "mrr": 1.0,
      "n": 8,
      "mode": "semantic"
    },
    {
      "agent": "fta.revenue",
      "intent": "fta.revenue.q1_financial_statements",
      "status": "skipped_bootstrap_failed",
      "recall": null,
      "mrr": null,
      "n": 10,
      "mode": null
    },
    {
      "agent": "fta.revenue",
      "intent": "fta.revenue.q2_revenue_by_segment",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "fta.revenue",
      "intent": "fta.revenue.q3_revenue_by_geography",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "fta.revenue",
      "intent": "fta.revenue.q4_customer_concentration",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 2,
      "mode": "semantic"
    },
    {
      "agent": "fta.revenue",
      "intent": "fta.revenue.q4_customer_concentration_fallback",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "fta.revenue",
      "intent": "fta.revenue.q5_quickbooks_pl",
      "status": "evaluated",
      "recall": 0.4615,
      "mrr": 1.0,
      "n": 8,
      "mode": "semantic"
    },
    {
      "agent": "kpi",
      "intent": "kpi.retrieve_delivery_model",
      "status": "evaluated",
      "recall": 0.0018,
      "mrr": 1.0,
      "n": 1,
      "mode": "semantic"
    },
    {
      "agent": "kpi",
      "intent": "kpi.retrieve_headcount_attrition",
      "status": "evaluated",
      "recall": 0.0018,
      "mrr": 1.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "kpi",
      "intent": "kpi.retrieve_healthcare_ops",
      "status": "evaluated",
      "recall": 0.0003,
      "mrr": 1.0,
      "n": 8,
      "mode": "semantic"
    },
    {
      "agent": "kpi",
      "intent": "kpi.retrieve_kpi_dashboard",
      "status": "evaluated",
      "recall": 0.1395,
      "mrr": 0.333,
      "n": 10,
      "mode": "semantic"
    },
    {
      "agent": "kpi",
      "intent": "kpi.retrieve_pipeline_backlog",
      "status": "evaluated",
      "recall": 0.0024,
      "mrr": 1.0,
      "n": 8,
      "mode": "semantic"
    },
    {
      "agent": "legal",
      "intent": "legal.contracts_vendors_platform",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 14,
      "mode": "semantic"
    },
    {
      "agent": "legal",
      "intent": "legal.employment",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "legal",
      "intent": "legal.insurance",
      "status": "evaluated",
      "recall": 0.1176,
      "mrr": 1.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "legal",
      "intent": "legal.ip_privacy",
      "status": "evaluated",
      "recall": 0.4706,
      "mrr": 1.0,
      "n": 8,
      "mode": "semantic"
    },
    {
      "agent": "legal",
      "intent": "legal.litigation",
      "status": "evaluated",
      "recall": 0.0588,
      "mrr": 1.0,
      "n": 7,
      "mode": "semantic"
    },
    {
      "agent": "profiler",
      "intent": "profiler.banked_vs_nonbanked",
      "status": "evaluated",
      "recall": 0.002,
      "mrr": 1.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "profiler",
      "intent": "profiler.business_description",
      "status": "evaluated",
      "recall": 0.01,
      "mrr": 1.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "profiler",
      "intent": "profiler.company_size_indicators",
      "status": "evaluated",
      "recall": 0.0013,
      "mrr": 1.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "profiler",
      "intent": "profiler.deal_type",
      "status": "evaluated",
      "recall": 0.01,
      "mrr": 1.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "profiler",
      "intent": "profiler.industry_overlay",
      "status": "evaluated",
      "recall": 0.01,
      "mrr": 1.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "profiler",
      "intent": "profiler.revenue_model",
      "status": "evaluated",
      "recall": 0.0,
      "mrr": 0.0,
      "n": 0,
      "mode": "empty"
    },
    {
      "agent": "profiler",
      "intent": "profiler.vertical_subsector",
      "status": "evaluated",
      "recall": 0.01,
      "mrr": 1.0,
      "n": 5,
      "mode": "semantic"
    },
    {
      "agent": "qoe",
      "intent": "qoe.retrieve_ebitda_bridge",
      "status": "evaluated",
      "recall": 0.0031,
      "mrr": 1.0,
      "n": 10,
      "mode": "semantic"
    },
    {
      "agent": "qoe",
      "intent": "qoe.retrieve_owner_comp_support",
      "status": "evaluated",
      "recall": 0.0018,
      "mrr": 1.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "qoe",
      "intent": "qoe.retrieve_qofe_report",
      "status": "skipped_bootstrap_failed",
      "recall": null,
      "mrr": null,
      "n": 0,
      "mode": null
    },
    {
      "agent": "qoe",
      "intent": "qoe.retrieve_revenue_footnotes",
      "status": "evaluated",
      "recall": 0.0018,
      "mrr": 1.0,
      "n": 6,
      "mode": "semantic"
    },
    {
      "agent": "qoe",
      "intent": "qoe.retrieve_revenue_quality",
      "status": "evaluated",
      "recall": 0.0025,
      "mrr": 1.0,
      "n": 8,
      "mode": "semantic"
    }
  ],
  "harness": [
    {
      "company_name": "Elder Care",
      "run_type": "baseline",
      "harness_status": "complete",
      "runs": "11",
      "last_run": "2026-07-15T23:51:17.956Z",
      "avg_intents": "49.0",
      "avg_fallback": "0.0",
      "avg_empty": "0.06342494714587738",
      "gate_pass_n": "0"
    },
    {
      "company_name": "Elder Care",
      "run_type": "enhancement",
      "harness_status": "complete",
      "runs": "2",
      "last_run": "2026-07-15T12:24:07.991Z",
      "avg_intents": "49.0",
      "avg_fallback": "0.0",
      "avg_empty": "0.03488372093023256",
      "gate_pass_n": "0"
    },
    {
      "company_name": "Elder Care",
      "run_type": "ablation",
      "harness_status": "complete",
      "runs": "4",
      "last_run": "2026-07-03T23:03:53.475Z",
      "avg_intents": "49.0",
      "avg_fallback": "0.0",
      "avg_empty": "0.09302325581395349",
      "gate_pass_n": "1"
    },
    {
      "company_name": "Clearsulting",
      "run_type": "pipeline",
      "harness_status": "complete",
      "runs": "6",
      "last_run": "2026-07-07T19:46:37.705Z",
      "avg_intents": "7",
      "avg_fallback": "0.0",
      "avg_empty": "0.0",
      "gate_pass_n": "0"
    },
    {
      "company_name": "Elder Care",
      "run_type": "pipeline",
      "harness_status": "complete",
      "runs": "19",
      "last_run": "2026-07-16T00:03:12.115Z",
      "avg_intents": "7",
      "avg_fallback": "0.0",
      "avg_empty": "0.0",
      "gate_pass_n": "0"
    },
    {
      "company_name": "GKF",
      "run_type": "pipeline",
      "harness_status": "complete",
      "runs": "8",
      "last_run": "2026-07-17T15:03:04.781Z",
      "avg_intents": "7",
      "avg_fallback": "1.0",
      "avg_empty": "0.0",
      "gate_pass_n": "0"
    },
    {
      "company_name": "SPG",
      "run_type": "pipeline",
      "harness_status": "complete",
      "runs": "6",
      "last_run": "2026-07-17T20:29:50.998Z",
      "avg_intents": "7",
      "avg_fallback": "1.0",
      "avg_empty": "0.0",
      "gate_pass_n": "0"
    }
  ],
  "provenance": [
    {
      "company_name": "Clearsulting",
      "runs": "6",
      "distinct_intents_in_provenance": "\u2014",
      "provenance_rows": "305",
      "avg_sim": "0.527",
      "avg_chars_alloc": "\u2014"
    },
    {
      "company_name": "Elder Care",
      "runs": "19",
      "distinct_intents_in_provenance": "\u2014",
      "provenance_rows": "6581",
      "avg_sim": "0.573",
      "avg_chars_alloc": "\u2014"
    },
    {
      "company_name": "GKF",
      "runs": "8",
      "distinct_intents_in_provenance": "\u2014",
      "provenance_rows": "218",
      "avg_sim": "0.0",
      "avg_chars_alloc": "\u2014"
    },
    {
      "company_name": "SPG",
      "runs": "6",
      "distinct_intents_in_provenance": "\u2014",
      "provenance_rows": "180",
      "avg_sim": "0.0",
      "avg_chars_alloc": "\u2014"
    }
  ],
  "prov_source": [
    {
      "company_name": "Clearsulting",
      "source_type": "text",
      "hits": "196",
      "avg_sim": "0.502",
      "avg_chars": null
    },
    {
      "company_name": "Clearsulting",
      "source_type": "vision",
      "hits": "56",
      "avg_sim": "0.557",
      "avg_chars": "1437.0"
    },
    {
      "company_name": "Clearsulting",
      "source_type": "table",
      "hits": "53",
      "avg_sim": "0.589",
      "avg_chars": "1472.8"
    },
    {
      "company_name": "Elder Care",
      "source_type": "text",
      "hits": "3366",
      "avg_sim": "0.539",
      "avg_chars": null
    },
    {
      "company_name": "Elder Care",
      "source_type": "vision",
      "hits": "1747",
      "avg_sim": "0.618",
      "avg_chars": "1351.0"
    },
    {
      "company_name": "Elder Care",
      "source_type": "table",
      "hits": "1468",
      "avg_sim": "0.598",
      "avg_chars": "1525.4"
    },
    {
      "company_name": "GKF",
      "source_type": "text",
      "hits": "208",
      "avg_sim": "0.0",
      "avg_chars": "1106.3"
    },
    {
      "company_name": "GKF",
      "source_type": "table",
      "hits": "9",
      "avg_sim": "0.0",
      "avg_chars": null
    },
    {
      "company_name": "GKF",
      "source_type": "vision",
      "hits": "1",
      "avg_sim": "0.0",
      "avg_chars": null
    }
  ],
  "emb_tier": [
    {
      "company_name": "Clearsulting",
      "priority_tier": "1",
      "embeddings": "1151",
      "files": "6"
    },
    {
      "company_name": "Clearsulting",
      "priority_tier": "2",
      "embeddings": "910",
      "files": "11"
    },
    {
      "company_name": "Clearsulting",
      "priority_tier": "3",
      "embeddings": "176",
      "files": "4"
    },
    {
      "company_name": "Elder Care",
      "priority_tier": "1",
      "embeddings": "3850",
      "files": "28"
    },
    {
      "company_name": "Elder Care",
      "priority_tier": "2",
      "embeddings": "31254",
      "files": "190"
    },
    {
      "company_name": "GKF",
      "priority_tier": "1",
      "embeddings": "1945",
      "files": "5"
    },
    {
      "company_name": "GKF",
      "priority_tier": "2",
      "embeddings": "1043",
      "files": "19"
    },
    {
      "company_name": "GKF",
      "priority_tier": "3",
      "embeddings": "50",
      "files": "16"
    }
  ],
  "page": [
    {
      "company_name": "Clearsulting",
      "chunks": "2237",
      "with_page": "1620",
      "min_page": "1",
      "max_page": "82",
      "distinct_sections": "518",
      "blank_section": "0"
    },
    {
      "company_name": "Elder Care",
      "chunks": "35104",
      "with_page": "4278",
      "min_page": "1",
      "max_page": "74",
      "distinct_sections": "1515",
      "blank_section": "0"
    },
    {
      "company_name": "GKF",
      "chunks": "3038",
      "with_page": "1237",
      "min_page": "1",
      "max_page": "484",
      "distinct_sections": "628",
      "blank_section": "0"
    }
  ],
  "eval_status_dist": {
    "evaluated": 43,
    "skipped_bootstrap_failed": 6
  },
  "embeddings_parity": [
    {
      "company": "Clearsulting",
      "chunks": 2237,
      "embeddings": 2237,
      "match": true
    },
    {
      "company": "Elder Care",
      "chunks": 35104,
      "embeddings": 35104,
      "match": true
    },
    {
      "company": "GKF",
      "chunks": 3038,
      "embeddings": 3038,
      "match": true
    },
    {
      "company": "SPG",
      "chunks": 71010,
      "embeddings": 71010,
      "match": true
    }
  ],
  "e2e": {
    "generated_at": "2026-07-17T20:57:51.131157+00:00",
    "t2_status": "complete",
    "t2_verdict": "PASS",
    "vs_index_uc13_ale": "MISSING",
    "vs_index_uc13_rows": 15080,
    "volumes": {
      "Clearsulting": {
        "orchestrator_bundle.yaml": {
          "path": "/Volumes/uc13_ale/analysis/reports/Clearsulting/orchestrator_bundle.yaml",
          "exists": true,
          "bytes": 39371
        },
        "tldr_one_pager.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/Clearsulting/tldr_one_pager.md",
          "exists": true,
          "bytes": 5539
        },
        "tldr_one_pager.docx": {
          "path": "/Volumes/uc13_ale/analysis/reports/Clearsulting/tldr_one_pager.docx",
          "exists": true,
          "bytes": 40386
        },
        "full_report.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/Clearsulting/full_report.md",
          "exists": true,
          "bytes": 33340
        }
      },
      "Elder Care": {
        "orchestrator_bundle.yaml": {
          "path": "/Volumes/uc13_ale/analysis/reports/Elder_Care/orchestrator_bundle.yaml",
          "exists": true,
          "bytes": 45545
        },
        "tldr_one_pager.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/Elder_Care/tldr_one_pager.md",
          "exists": true,
          "bytes": 8685
        },
        "tldr_one_pager.docx": {
          "path": "/Volumes/uc13_ale/analysis/reports/Elder_Care/tldr_one_pager.docx",
          "exists": true,
          "bytes": 41892
        },
        "full_report.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/Elder_Care/full_report.md",
          "exists": true,
          "bytes": 37977
        }
      },
      "GKF": {
        "orchestrator_bundle.yaml": {
          "path": "/Volumes/uc13_ale/analysis/reports/GKF/orchestrator_bundle.yaml",
          "exists": true,
          "bytes": 34044
        },
        "tldr_one_pager.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/GKF/tldr_one_pager.md",
          "exists": true,
          "bytes": 7192
        },
        "tldr_one_pager.docx": {
          "path": "/Volumes/uc13_ale/analysis/reports/GKF/tldr_one_pager.docx",
          "exists": true,
          "bytes": 41001
        },
        "full_report.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/GKF/full_report.md",
          "exists": true,
          "bytes": 27558
        }
      },
      "SPG": {
        "orchestrator_bundle.yaml": {
          "path": "/Volumes/uc13_ale/analysis/reports/SPG/orchestrator_bundle.yaml",
          "exists": true,
          "bytes": 32542
        },
        "tldr_one_pager.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/SPG/tldr_one_pager.md",
          "exists": true,
          "bytes": 6228
        },
        "tldr_one_pager.docx": {
          "path": "/Volumes/uc13_ale/analysis/reports/SPG/tldr_one_pager.docx",
          "exists": true,
          "bytes": 40538
        },
        "full_report.md": {
          "path": "/Volumes/uc13_ale/analysis/reports/SPG/full_report.md",
          "exists": true,
          "bytes": 27093
        }
      }
    },
    "tldr_h1": {
      "Clearsulting": "# Clearsulting \u2014 Executive Summary",
      "Elder Care": "# Elder Care \u2014 Executive Summary",
      "GKF": "# GKF \u2014 Executive Summary",
      "SPG": "# SPG \u2014 Executive Summary"
    },
    "t2_word_counts": {
      "Clearsulting": 847,
      "Elder Care": 1325,
      "GKF": 1070,
      "SPG": 931
    },
    "missing_by_workstream": [
      {
        "company_name": "Clearsulting",
        "ws": "BUSINESS_MODEL",
        "missing_files": "1"
      },
      {
        "company_name": "Elder Care",
        "ws": "FINANCIAL",
        "missing_files": "112"
      },
      {
        "company_name": "Elder Care",
        "ws": "LEGAL",
        "missing_files": "38"
      },
      {
        "company_name": "Elder Care",
        "ws": "KPI_OPS",
        "missing_files": "27"
      },
      {
        "company_name": "Elder Care",
        "ws": "BACKGROUND",
        "missing_files": "6"
      },
      {
        "company_name": "SPG",
        "ws": "LEGAL",
        "missing_files": "31"
      },
      {
        "company_name": "SPG",
        "ws": "BACKGROUND",
        "missing_files": "5"
      },
      {
        "company_name": "SPG",
        "ws": "FINANCIAL",
        "missing_files": "4"
      },
      {
        "company_name": "SPG",
        "ws": "QUALITY_EARNINGS",
        "missing_files": "2"
      },
      {
        "company_name": "SPG",
        "ws": "KPI_OPS",
        "missing_files": "1"
      }
    ],
    "legal_doc_count": [
      {
        "company_name": "Elder Care",
        "legal_docs": "112"
      },
      {
        "company_name": "GKF",
        "legal_docs": "4"
      },
      {
        "company_name": "SPG",
        "legal_docs": "181"
      }
    ]
  }
};

const COMPANIES = ["Clearsulting", "Elder Care", "GKF", "SPG"] as const;
type Company = (typeof COMPANIES)[number];

function fmt(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return n.toFixed(digits);
}

function uploadOf(c: string) {
  return DATA.upload.find((r) => r.company === c);
}
function chunksOf(c: string) {
  return DATA.chunks.find((r) => r.company === c);
}
function joinOf(c: string) {
  return DATA.join.find((r) => r.company === c);
}

export default function Uc13CompanyDataAnalysis() {
  const [company, setCompany] = useCanvasState<Company>("company", "Elder Care");
  const up = uploadOf(company);
  const ch = chunksOf(company);
  const jo = joinOf(company);
  const formats = DATA.formats[company] || {};
  const sources = DATA.source_types[company] || {};
  const fileTypes = DATA.file_types[company] || {};
  const conf = DATA.confidence[company] || {};
  const workstreams = DATA.workstreams[company] || [];
  const embWs = DATA.emb_ws_text[company] || [];
  const profile = DATA.profiles.find((r) => r.company_name === company);
  const agents = DATA.agents[company];
  const page = DATA.page.find((r) => r.company_name === company);
  const embTier = DATA.emb_tier.filter((r) => r.company_name === company);
  const prov = DATA.provenance.find((r) => r.company_name === company);
  const provSrc = DATA.prov_source.filter((r) => r.company_name === company);
  const harness = DATA.harness.filter((r) => r.company_name === company);

  const corpusChart = DATA.upload.map((r) => ({
    label: r.company.replace("Elder Care", "Elder"),
    files: r.files,
    mb: r.mb,
  }));

  const chunkChart = DATA.chunks.map((r) => ({
    label: r.company.replace("Elder Care", "Elder"),
    chunks: r.chunks,
    wordsM: +(r.words / 1_000_000).toFixed(2),
    tokensM: +(r.tokens4 / 1_000_000).toFixed(2),
  }));

  const ingestChart = DATA.join.map((r) => ({
    label: r.company.replace("Elder Care", "Elder"),
    pct: r.pct,
  }));

  const sourceChart = Object.entries(sources).map(([k, v]) => ({
    label: k,
    chunks: v.chunks,
    wordsK: +(v.words / 1000).toFixed(1),
  }));

  const wsDocsChart = workstreams.map((r) => ({
    label: r.ws.replace("QUALITY_EARNINGS", "QoE").replace("BUSINESS_MODEL", "BM"),
    docs: r.docs,
    should_parse: r.should_parse,
  }));

  const embCharsChart = embWs.map((r) => ({
    label: r.ws.replace("QUALITY_EARNINGS", "QoE").replace("BUSINESS_MODEL", "BM"),
    charsM: +(r.chars / 1_000_000).toFixed(2),
    embeddings: r.embeddings,
  }));

  const confChart = ["high", "medium", "low"].filter((k) => conf[k] != null).map((k) => ({
    label: k,
    docs: conf[k] || 0,
  }));

  const intentRows = DATA.intents.map((r) => ({
    Agent: r.agent,
    Intent: r.intent,
    Status: r.status,
    Recall: r.recall == null ? "—" : String(r.recall),
    MRR: r.mrr == null ? "—" : String(r.mrr),
    Results: String(r.n),
    Mode: r.mode || "—",
  }));

  const agentRows = agents
    ? Object.entries(agents).map(([name, a]) => ({
        Agent: name,
        Gaps: String(a.gaps),
        "Exec chars": String(a.exec || "—"),
        "Citation chars": String(a.citations),
        Detail: Object.entries(a.extra || {})
          .map(([k, v]) => k + "=" + String(v))
          .join("; ") || "—",
      }))
    : [];

  const wsRows = workstreams.map((r) => ({
    Workstream: r.ws,
    Docs: String(r.docs),
    "Should parse": String(r.should_parse),
    High: String(r.high),
    Med: String(r.med),
    Low: String(r.low),
    "Avg tier": String(r.avg_tier),
  }));

  const formatRows = Object.entries(formats).map(([k, v]) => ({ Format: k, Files: String(v) }));
  const fileTypeRows = Object.entries(fileTypes).map(([k, v]) => ({
    "File type": k,
    Chunks: String(v.chunks),
    Files: String(v.files),
    Chars: fmt(v.chars),
  }));

  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>UC-13 company data analysis</H1>
        <Text tone="secondary">
          Live warehouse probe of uc13_ale — uploads, classification, chunk/embedding text volume, agent richness, and Elder Care retrieval intents (baseline_1aeb0ace584a). E2E readiness refresh 2026-07-17 — T2 all-4 PASS; uc13_ale VS index missing.
        </Text>
      </Stack>

      <Grid columns={4} gap={12}>
        <Stat value="4" label="Companies in SharePoint" />
        <Stat value="4" label="Fully chunked" tone="success" />
        <Stat value="0" label="VS index (uc13_ale)" tone="danger" />
        <Stat value="49" label="Baseline intents (Elder Care)" />
      </Grid>

      <Callout tone="danger" title="uc13_ale vector index missing">
        Delta has ~109k embeddings across 4 companies but `uc13_ale.ingestion.embeddings_index` does not exist. GKF and SPG pipeline harness runs show fallback_rate=1.0 and provenance avg_sim=0. Run setup_vector_search / Cell 2b for catalog=uc13_ale before trusting semantic retrieval on new companies.
      </Callout>
      <Callout tone="success" title="Wed T2 baseline — all 4 PASS">
        All companies have orchestrator bundle + tldr_one_pager.md/.docx titled Executive Summary on uc13_ale (see `.dev/t2_baseline_run_log.json`). SPG: 71,010 chunks/embeddings, agents rendered Jul 17 salvage run.
      </Callout>

      <H2>Cross-company corpus</H2>
      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>Uploaded size (MB) by company</H3>
          <BarChart
            categories={corpusChart.map((d) => d.label)}
            series={[{ name: "MB uploaded", data: corpusChart.map((d) => d.mb) }]}
            height={220}
          />
          <Text tone="secondary" size="small">Source: uc13_ale.ingestion.upload_log · sum(size_bytes)</Text>
        </Stack>
        <Stack gap={8}>
          <H3>Ingested text volume (M words)</H3>
          <BarChart
            categories={chunkChart.map((d) => d.label)}
            series={[{ name: "Words (M)", data: chunkChart.map((d) => d.wordsM) }]}
            height={220}
          />
          <Text tone="secondary" size="small">Source: chunks · whitespace token count on chunk_text</Text>
        </Stack>
      </Grid>

      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>Approx tokens (chars/4, millions)</H3>
          <BarChart
            categories={chunkChart.map((d) => d.label)}
            series={[{ name: "Tokens M", data: chunkChart.map((d) => d.tokensM) }]}
            height={200}
          />
        </Stack>
        <Stack gap={8}>
          <H3>should_parse → chunks ingest %</H3>
          <BarChart
            categories={ingestChart.map((d) => d.label)}
            series={[{ name: "% ingested", data: ingestChart.map((d) => d.pct) }]}
            height={200}
          />
          <Text tone="secondary" size="small">Elder Care only 53.5% of should_parse files present in chunks</Text>
        </Stack>
      </Grid>

      <Table
        headers={["Company", "Files", "MB", "Chunks", "Words", "≈Tokens", "Ingest %", "Profile"]}
        rows={COMPANIES.map((c) => {
          const u = uploadOf(c)!;
          const k = chunksOf(c);
          const j = joinOf(c)!;
          const pr = DATA.profiles.find((r) => r.company_name === c);
          return [
            c,
            String(u.files),
            String(u.mb),
            k ? String(k.chunks) : "0",
            k ? fmt(k.words) : "—",
            k ? fmt(k.tokens4) : "—",
            String(j.pct) + "%",
            pr ? String(pr.overlay_confidence) : "missing",
          ];
        })}
        rowTone={COMPANIES.map((c) => (c === "SPG" ? "warning" : undefined))}
      />

      <Divider />

      <Row gap={12} align="center">
        <H2>Company drill-down</H2>
        <Select
          value={company}
          onChange={(v) => setCompany(v as Company)}
          options={COMPANIES.map((c) => ({ value: c, label: c }))}
        />
      </Row>

      <Grid columns={4} gap={12}>
        <Stat value={up ? String(up.files) : "0"} label="Uploaded files" />
        <Stat value={up ? String(up.mb) + " MB" : "—"} label="Corpus size" />
        <Stat value={ch ? String(ch.chunks) : "0"} label="Chunks" tone={ch ? "success" : "warning"} />
        <Stat
          value={jo ? String(jo.pct) + "%" : "—"}
          label="should_parse ingested"
          tone={jo && jo.pct >= 90 ? "success" : jo && jo.pct > 0 ? "warning" : "danger"}
        />
      </Grid>

      {ch ? (
        <Grid columns={4} gap={12}>
          <Stat value={fmt(ch.chars)} label="Total chars" />
          <Stat value={fmt(ch.words)} label="Total words" />
          <Stat value={fmt(ch.tokens4)} label="Approx tokens (chars/4)" />
          <Stat value={String(ch.avg_chars)} label={`Avg chars/chunk (p50 ${String(ch.p50)})`} />
        </Grid>
      ) : (
        <Callout tone="warning" title="No chunk corpus yet">
          Classification exists for {company}, but ingestion_parser has not written chunks/embeddings.
        </Callout>
      )}

      {profile && (
        <Card>
          <CardHeader trailing={<Pill tone="info">{String(profile.overlay_confidence)} conf</Pill>}>
            Company profile
          </CardHeader>
          <CardBody>
            <Text>
              Overlay {String(profile.industry_overlay)} · deal {String(profile.deal_type)} · banked {String(profile.banked)} · profiler gaps {String(profile.n_gaps)} · description {String(profile.desc_chars)} chars
            </Text>
          </CardBody>
        </Card>
      )}

      <Grid columns={2} gap={16}>
        <Stack gap={8}>
          <H3>Upload formats</H3>
          <Table headers={["Format", "Files"]} rows={formatRows.map((r) => [r.Format, r.Files])} />
        </Stack>
        <Stack gap={8}>
          <H3>Classifier confidence</H3>
          {confChart.length > 0 ? (
            <BarChart
              categories={confChart.map((d) => d.label)}
              series={[{ name: "Docs", data: confChart.map((d) => d.docs) }]}
              height={180}
            />
          ) : (
            <Text tone="secondary">No classification rows</Text>
          )}
        </Stack>
      </Grid>

      <H3>Workstream classification (exploded)</H3>
      {wsDocsChart.length > 0 && (
        <BarChart
          categories={wsDocsChart.map((d) => d.label)}
          series={[
            { name: "Docs tagged", data: wsDocsChart.map((d) => d.docs) },
            { name: "should_parse", data: wsDocsChart.map((d) => d.should_parse) },
          ]}
          height={220}
        />
      )}
      {wsRows.length > 0 && (
        <Table
          headers={["Workstream", "Docs", "Should parse", "High", "Med", "Low", "Avg tier"]}
          rows={wsRows.map((r) => [r.Workstream, r.Docs, r["Should parse"], r.High, r.Med, r.Low, r["Avg tier"]])}
        />
      )}

      {company === "Clearsulting" && (
        <Callout tone="danger" title="Clearsulting has zero LEGAL-tagged docs">
          Explains empty legal registers and historical 0/11 legal checklist — pipeline can be green while diligence surface is absent.
        </Callout>
      )}
      {company === "GKF" && (
        <Callout tone="warning" title="GKF retrieval provenance avg_sim = 0">
          Recent pipeline harness runs show fallback_rate=1.0 — semantic path not scoring; keyword/fallback context only. Agents still wrote rows Jul 17.
        </Callout>
      )}
      {company === "SPG" && (
        <Callout tone="warning" title="SPG retrieval on keyword fallback">
          Largest corpus (71k chunks) but pipeline harness fallback_rate=1.0 and provenance avg_sim=0 — same root cause as GKF: missing uc13_ale.ingestion.embeddings_index. Agents + exec summary rendered Jul 17.
        </Callout>
      )}

      {Object.keys(sources).length > 0 && (
        <>
          <H3>Chunk source_type mix</H3>
          <BarChart
            categories={sourceChart.map((d) => d.label)}
            series={[
              { name: "Chunks", data: sourceChart.map((d) => d.chunks) },
              { name: "Words (k)", data: sourceChart.map((d) => d.wordsK) },
            ]}
            height={220}
          />
          <Table
            headers={["Source", "Chunks", "Chars", "Words"]}
            rows={Object.entries(sources).map(([k, v]) => [k, String(v.chunks), fmt(v.chars), fmt(v.words)])}
          />
        </>
      )}

      {fileTypeRows.length > 0 && (
        <>
          <H3>Chunk file_type mix</H3>
          <Table
            headers={["File type", "Chunks", "Files", "Chars"]}
            rows={fileTypeRows.map((r) => [r["File type"], r.Chunks, r.Files, r.Chars])}
          />
        </>
      )}

      {embWs.length > 0 && (
        <>
          <H3>Embedded text by workstream (joined chunks×embeddings)</H3>
          <BarChart
            categories={embCharsChart.map((d) => d.label)}
            series={[{ name: "Chars (M)", data: embCharsChart.map((d) => d.charsM) }]}
            height={220}
          />
          <Table
            headers={["Workstream", "Embeddings", "Chars", "Words", "Avg chars"]}
            rows={embWs.map((r) => [r.ws, String(r.embeddings), fmt(r.chars), fmt(r.words), String(r.avg_chars)])}
          />
        </>
      )}

      {embTier.length > 0 && (
        <>
          <H3>Embedding priority tiers</H3>
          <Table
            headers={["Tier", "Embeddings", "Files"]}
            rows={embTier.map((r) => [String(r.priority_tier), String(r.embeddings), String(r.files)])}
          />
        </>
      )}

      {page && (
        <Text tone="secondary">
          Page metadata: {String(page.with_page)}/{String(page.chunks)} chunks have pages (max page {String(page.max_page)}); {String(page.distinct_sections)} distinct section headers.
        </Text>
      )}

      <Divider />
      <H2>Agent output richness — {company}</H2>
      {agentRows.length > 0 ? (
        <Table
          headers={["Agent", "Gaps", "Exec chars", "Citation chars", "Detail"]}
          rows={agentRows.map((r) => [r.Agent, r.Gaps, r["Exec chars"], r["Citation chars"], r.Detail])}
        />
      ) : (
        <Text tone="secondary">No analysis rows for this company yet.</Text>
      )}

      <Divider />
      <H2>Retrieval intents & provenance</H2>
      <Text tone="secondary">
        Gold-label intent scoring exists only for Elder Care baseline ({Object.entries(DATA.eval_status_dist).map(([k, v]) => k + ":" + v).join(", ")}). Other companies have pipeline provenance only.
      </Text>

      {harness.length > 0 && (
        <Table
          headers={["Run type", "Status", "Runs", "Last run", "Avg intents", "Fallback", "Empty"]}
          rows={harness.map((r) => [
            String(r.run_type),
            String(r.harness_status),
            String(r.runs),
            String(r.last_run).slice(0, 10),
            String(Number(r.avg_intents).toFixed(1)),
            String(Number(r.avg_fallback).toFixed(2)),
            String(Number(r.avg_empty).toFixed(3)),
          ])}
        />
      )}

      {prov && (
        <Grid columns={4} gap={12}>
          <Stat value={String(prov.runs)} label="Provenance runs" />
          <Stat value={String(prov.distinct_intents_in_provenance)} label="Distinct intents seen" />
          <Stat value={String(prov.provenance_rows)} label="Provenance rows" />
          <Stat value={String(prov.avg_sim)} label="Avg sim score" />
        </Grid>
      )}

      {provSrc.length > 0 && (
        <Table
          headers={["Source type", "Hits", "Avg sim", "Avg chars alloc"]}
          rows={provSrc.map((r) => [
            String(r.source_type),
            String(r.hits),
            String(r.avg_sim),
            r.avg_chars == null ? "—" : String(r.avg_chars),
          ])}
        />
      )}

      {company === "Elder Care" && (
        <>
          <H3>Baseline intent rollup by agent</H3>
          <Table
            headers={["Agent", "Intents", "Avg recall@10", "Avg MRR", "Avg results", "Empty"]}
            rows={DATA.intent_rollup.map((r) => [
              r.agent,
              String(r.intents),
              r.avg_recall == null ? "—" : String(r.avg_recall),
              r.avg_mrr == null ? "—" : String(r.avg_mrr),
              String(r.avg_results),
              String(r.empty_n),
            ])}
          />
          <H3>All 49 baseline intents</H3>
          <Table
            headers={["Agent", "Intent", "Status", "Recall@10", "MRR", "Results", "Mode"]}
            rows={intentRows.map((r) => [r.Agent, r.Intent, r.Status, r.Recall, r.MRR, r.Results, r.Mode])}
          />
        </>
      )}

      <Spacer />
      <Text tone="secondary" size="small">
        Catalog uc13_ale · tokens ≈ char_count/4 · words = whitespace split on chunk_text · raw JSON also in repo .dev/tmp_deep_data_analysis.json
      </Text>
    </Stack>
  );
}
