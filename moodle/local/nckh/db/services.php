<?php

defined('MOODLE_INTERNAL') || die();

$functions = [
    'local_nckh_upsert_question' => [
        'classname' => 'local_nckh\\external\\upsert_question',
        'methodname' => 'execute',
        'description' => 'Idempotently import one versioned QBankCTU question.',
        'type' => 'write',
        'ajax' => false,
        'capabilities' => 'local/nckh:publishquestion',
    ],
    'local_nckh_get_question' => [
        'classname' => 'local_nckh\\external\\get_question',
        'methodname' => 'execute',
        'description' => 'Read QBankCTU provenance for a Moodle question.',
        'type' => 'read',
        'ajax' => false,
        'capabilities' => 'local/nckh:publishquestion',
    ],
    'local_nckh_find_question' => [
        'classname' => 'local_nckh\\external\\find_question',
        'methodname' => 'execute',
        'description' => 'Find a Moodle question by QBankCTU idempotency key.',
        'type' => 'read',
        'ajax' => false,
        'capabilities' => 'local/nckh:publishquestion',
    ],
];

$services = [
    'QBankCTU question bank connector' => [
        'functions' => array_keys($functions),
        'restrictedusers' => 1,
        'enabled' => 1,
        'shortname' => 'local_nckh_questionbank',
    ],
];
