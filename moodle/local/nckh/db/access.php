<?php

defined('MOODLE_INTERNAL') || die();

$capabilities = [
    'local/nckh:publishquestion' => [
        'captype' => 'write',
        'contextlevel' => CONTEXT_MODULE,
        'archetypes' => [
            'manager' => CAP_ALLOW,
            'editingteacher' => CAP_ALLOW,
        ],
    ],
];
