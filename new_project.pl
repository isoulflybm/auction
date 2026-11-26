#!/usr/bin/perl

use strict;
use warnings;
use LWP::UserAgent;
use JSON;
use Time::HiRes qw(sleep);

my $base_url = 'https://portal.sot.kg/api/v1/lot/';
my $limit = 10;
my $page = 1;
my @all_items;

my $ua = LWP::UserAgent->new;
$ua->timeout(10);

my $json_parser = JSON->new->utf8;

while (1) {
    my $url = "$base_url?page=$page&limit=$limit";
    print "Страница $page: $url\n";

    my $response = $ua->get($url);

    if (!$response->is_success) {
        warn "Ошибка запроса: " . $response->status_line;
        last;
    }

    my $data;
    eval {
        $data = $json_parser->decode($response->decoded_content);
    };
    if ($@) {
        warn "Ошибка парсинга JSON на странице $page: $@";
        last;
    }

    my $items = $data->{items} || [];
    last unless @$items;

    push @all_items, @$items;

    my $max_page = $data->{max_next_page} || $page;
    last if $page >= $max_page;

    $page++;
    sleep(1);  # Не спамим
}

# Сохраняем итоговый JSON
open my $fh, '>', 'sot_kg_data.json' or die "Не могу записать файл: $!";
print $fh $json_parser->pretty->encode(\@all_items);
close $fh;

print "\nГотово! Получено ", scalar(@all_items), " объектов. Сохранил в sot_kg_data.json\n";
