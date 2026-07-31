use std::collections::HashMap;

pub struct LruCache {
    capacity: usize,
    map: HashMap<i32, i32>,
    order: Vec<i32>, // du moins récent au plus récent
}

impl LruCache {
    pub fn new(capacity: usize) -> Self {
        Self {
            capacity,
            map: HashMap::new(),
            order: Vec::new(),
        }
    }

    fn touch(&mut self, key: i32) {
        if let Some(pos) = self.order.iter().position(|&k| k == key) {
            self.order.remove(pos);
        }
        self.order.push(key);
    }

    pub fn get(&mut self, key: i32) -> Option<i32> {
        match self.map.get(&key) {
            Some(&value) => {
                self.touch(key);
                Some(value)
            }
            None => None,
        }
    }

    pub fn put(&mut self, key: i32, value: i32) {
        let is_new = self.map.insert(key, value).is_none();
        if is_new && self.map.len() > self.capacity {
            let lru = self.order.remove(0);
            self.map.remove(&lru);
        }
        self.touch(key);
    }

    pub fn len(&self) -> usize {
        self.map.len()
    }

    pub fn is_empty(&self) -> bool {
        self.map.is_empty()
    }
}
