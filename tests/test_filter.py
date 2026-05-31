from wb_parser_playwright import filter_reviews_by_rating


def _reviews():
    return [
        {'rating': 1, 'text': 'a'},
        {'rating': 2, 'text': 'b'},
        {'rating': 3, 'text': 'c'},
        {'rating': 4, 'text': 'd'},
        {'rating': 5, 'text': 'e'},
        {'rating': 0, 'text': 'no rating'},
    ]


def test_all_returns_everything():
    assert filter_reviews_by_rating(_reviews(), 'all') == _reviews()


def test_single_star():
    result = filter_reviews_by_rating(_reviews(), '3')
    assert [r['rating'] for r in result] == [3]


def test_range_1_2():
    result = filter_reviews_by_rating(_reviews(), '1-2')
    assert [r['rating'] for r in result] == [1, 2]


def test_range_1_3():
    result = filter_reviews_by_rating(_reviews(), '1-3')
    assert [r['rating'] for r in result] == [1, 2, 3]


def test_range_4_5():
    result = filter_reviews_by_rating(_reviews(), '4-5')
    assert [r['rating'] for r in result] == [4, 5]


def test_custom_set():
    result = filter_reviews_by_rating(_reviews(), '2,5')
    assert [r['rating'] for r in result] == [2, 5]


def test_empty_list():
    assert filter_reviews_by_rating([], '1-3') == []


def test_rating_zero_excluded_by_filters():
    result = filter_reviews_by_rating(_reviews(), '1-3')
    assert all(r['rating'] != 0 for r in result)


def test_unknown_filter_returns_all():
    assert filter_reviews_by_rating(_reviews(), 'garbage') == _reviews()


def test_out_of_range_single_star_returns_all():
    assert filter_reviews_by_rating(_reviews(), '9') == _reviews()


def test_unsupported_range_returns_all():
    assert filter_reviews_by_rating(_reviews(), '2-4') == _reviews()

