use task::LruCache;

#[test]
fn leetcode_146_example() {
    let mut c = LruCache::new(2);
    c.put(1, 1);
    c.put(2, 2);
    assert_eq!(c.get(1), Some(1));
    c.put(3, 3);
    assert_eq!(c.get(2), None);
    c.put(4, 4);
    assert_eq!(c.get(1), None);
    assert_eq!(c.get(3), Some(3));
    assert_eq!(c.get(4), Some(4));
}

#[test]
fn miss_on_empty_cache() {
    let mut c = LruCache::new(2);
    assert_eq!(c.get(42), None);
    assert!(c.is_empty());
    assert_eq!(c.len(), 0);
}

#[test]
fn update_existing_key_does_not_grow() {
    let mut c = LruCache::new(2);
    c.put(1, 1);
    c.put(1, 10);
    assert_eq!(c.len(), 1);
    assert_eq!(c.get(1), Some(10));
}

#[test]
fn update_existing_key_refreshes_recency() {
    let mut c = LruCache::new(2);
    c.put(1, 1);
    c.put(2, 2);
    c.put(1, 100); // 1 devient le plus récent, 2 devient le plus ancien
    c.put(3, 3); // évince 2
    assert_eq!(c.get(2), None);
    assert_eq!(c.get(1), Some(100));
    assert_eq!(c.get(3), Some(3));
}

#[test]
fn get_refreshes_recency() {
    let mut c = LruCache::new(3);
    c.put(1, 1);
    c.put(2, 2);
    c.put(3, 3);
    assert_eq!(c.get(1), Some(1)); // ordre LRU : 2, 3, 1
    c.put(4, 4); // évince 2
    assert_eq!(c.get(2), None);
    assert_eq!(c.get(1), Some(1));
    assert_eq!(c.get(3), Some(3));
    assert_eq!(c.get(4), Some(4));
}

#[test]
fn missing_get_has_no_side_effect() {
    let mut c = LruCache::new(2);
    c.put(1, 1);
    c.put(2, 2);
    assert_eq!(c.get(99), None);
    c.put(3, 3); // évince 1, pas 2
    assert_eq!(c.get(1), None);
    assert_eq!(c.get(2), Some(2));
}

#[test]
fn capacity_one() {
    let mut c = LruCache::new(1);
    c.put(1, 1);
    c.put(2, 2);
    assert_eq!(c.get(1), None);
    assert_eq!(c.get(2), Some(2));
    assert_eq!(c.len(), 1);
}

#[test]
fn len_never_exceeds_capacity() {
    let mut c = LruCache::new(3);
    for i in 0..50 {
        c.put(i, i * 2);
        assert!(c.len() <= 3);
    }
    assert_eq!(c.len(), 3);
    assert_eq!(c.get(49), Some(98));
    assert_eq!(c.get(48), Some(96));
    assert_eq!(c.get(47), Some(94));
    assert_eq!(c.get(46), None);
}

#[test]
fn negative_keys_and_values() {
    let mut c = LruCache::new(2);
    c.put(-1, -100);
    c.put(-2, 0);
    assert_eq!(c.get(-1), Some(-100));
    assert_eq!(c.get(-2), Some(0));
}

#[test]
fn stress_repeated_access_keeps_hot_key() {
    let mut c = LruCache::new(2);
    c.put(0, 0);
    for i in 1..20 {
        assert_eq!(c.get(0), Some(0));
        c.put(i, i);
    }
    assert_eq!(c.get(0), Some(0));
    assert_eq!(c.get(19), Some(19));
    assert_eq!(c.get(18), None);
}
