// Register the four test-SIM subscribers (one per DU/UE) in the Open5GS Mongo database,
// idempotently. IMSIs 001010000000001..004 share the srsUE soft-SIM credentials
// (ran_lib.UE_K / UE_OPC); DNN "internet", SST 1, 5QI 9.
const k = "00112233445566778899aabbccddeeff";
const opc = "63BFA50EE6523365FF14C1F45F88737D";
const imsis = [
    "001010000000001",
    "001010000000002",
    "001010000000003",
    "001010000000004",
];

db = db.getSiblingDB("open5gs");
for (const imsi of imsis) {
    if (db.subscribers.countDocuments({imsi: imsi}) > 0) {
        print("subscriber " + imsi + " already present");
        continue;
    }
    db.subscribers.insertOne({
        schema_version: NumberInt(1),
        imsi: imsi,
        msisdn: [],
        imeisv: [],
        mme_host: [],
        mme_realm: [],
        purge_flag: [],
        security: {k: k, op: null, opc: opc, amf: "8000", sqn: NumberLong(64)},
        ambr: {
            downlink: {value: NumberInt(1), unit: NumberInt(3)},
            uplink: {value: NumberInt(1), unit: NumberInt(3)}
        },
        slice: [{
            sst: NumberInt(1),
            default_indicator: true,
            session: [{
                name: "internet",
                type: NumberInt(3),
                qos: {
                    index: NumberInt(9),
                    arp: {
                        priority_level: NumberInt(8),
                        pre_emption_capability: NumberInt(1),
                        pre_emption_vulnerability: NumberInt(1)
                    }
                },
                ambr: {
                    downlink: {value: NumberInt(1), unit: NumberInt(3)},
                    uplink: {value: NumberInt(1), unit: NumberInt(3)}
                }
            }]
        }],
        access_restriction_data: 32,
        network_access_mode: 0,
        subscriber_status: 0,
        operator_determined_barring: 0,
        subscribed_rau_tau_timer: 12,
        __v: 0
    });
    print("subscriber " + imsi + " inserted");
}
